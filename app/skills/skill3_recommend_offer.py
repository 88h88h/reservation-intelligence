"""Agent skill 3: when occupancy is low, recommend a promotional offer
on a menu item to help fill seats without eroding margin on business
that would have happened anyway.

Unlike skills 1 and 2, this one's autonomy boundary is graduated, not
suggest-only: a discount within the menu item's pre-approved
maxAutoDiscount ceiling is low-risk enough to go live immediately, no
separate staff step, so this skill writes the resulting Offer row
itself. A discount above that ceiling is created as
PENDING_CONFIRMATION instead, waiting on staff approval.

The LLM never sees maxAutoDiscount when proposing a discount, only the
occupancy signal and the menu item's own price, so its proposal
reflects an honest judgment call rather than a number chosen to game
the ceiling. The ceiling is applied afterward, in code, not by the LLM.
"""

import sqlite3

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.repositories import menu_item_repo, offer_repo, restaurant_repo
from app.services.occupancy_service import current_occupancy_ratio

load_dotenv()

_llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite")

LOW_OCCUPANCY_THRESHOLD = 0.4


class OfferProposal(BaseModel):
    has_recommendation: bool = Field(description="Whether a promotional offer is warranted right now")
    menu_item_id: int | None = Field(default=None)
    proposed_discount: float | None = Field(default=None, description="Dollar amount off the item's price")
    reasoning: str = Field(description="Explanation referencing the actual occupancy number")


_structured_llm = _llm.with_structured_output(OfferProposal)

PROMPT = """Current occupancy at {restaurant_name}: {occupancy_pct:.0f}% of tables confirmed right now.

Menu items available to discount:
{menu_items}

Occupancy is low enough that a promotional offer could help fill seats and drive extra revenue,
without eroding margin on business that would have happened anyway. Recommend ONE menu item to
discount and by how much (a dollar amount off its price), or say no offer is warranted. Prefer a
modest discount that still leaves a healthy margin over a steep one. Explain your reasoning in one
or two sentences, referencing the actual occupancy number.
"""


class OfferResult(BaseModel):
    has_recommendation: bool
    offer_id: int | None = None
    menu_item_id: int | None = None
    proposed_discount: float | None = None
    status: str | None = None
    reasoning: str


def _format_menu_items(items: list[sqlite3.Row]) -> str:
    return "\n".join(f"- menu_item_id={i['id']}, name={i['name']}, price=${i['price']:.2f}" for i in items)


def recommend_offer(conn: sqlite3.Connection, *, restaurant_id: int) -> OfferResult:
    occupancy_ratio = current_occupancy_ratio(conn, restaurant_id)
    menu_items = menu_item_repo.list_for_restaurant(conn, restaurant_id)

    if not menu_items:
        return OfferResult(has_recommendation=False, reasoning="No menu items configured for this restaurant.")

    if occupancy_ratio > LOW_OCCUPANCY_THRESHOLD:
        return OfferResult(
            has_recommendation=False,
            reasoning=f"Occupancy is {occupancy_ratio * 100:.0f}%, not low enough to warrant a promotional offer.",
        )

    restaurant = restaurant_repo.get_by_id(conn, restaurant_id)
    prompt = PROMPT.format(
        restaurant_name=restaurant["name"],
        occupancy_pct=occupancy_ratio * 100,
        menu_items=_format_menu_items(menu_items),
    )
    proposal = _structured_llm.invoke(prompt)

    if not proposal.has_recommendation or proposal.menu_item_id is None:
        return OfferResult(has_recommendation=False, reasoning=proposal.reasoning)

    menu_item = menu_item_repo.get_by_id(conn, proposal.menu_item_id)
    status = "ACTIVE" if proposal.proposed_discount <= menu_item["max_auto_discount"] else "PENDING_CONFIRMATION"

    offer_id = offer_repo.insert_offer(
        conn, menu_item_id=proposal.menu_item_id, proposed_value=proposal.proposed_discount, status=status
    )

    return OfferResult(
        has_recommendation=True,
        offer_id=offer_id,
        menu_item_id=proposal.menu_item_id,
        proposed_discount=proposal.proposed_discount,
        status=status,
        reasoning=proposal.reasoning,
    )
