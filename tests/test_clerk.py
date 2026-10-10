import unittest

from app.decide import BUY, HOLD, SEE, decide
from app.desk import build_plan
from app.followup import choose_followup
from app.evidence import Article, Listing, Page, Place, listings_from, places_from
from app.market import focus_listings
from app.money import format_inr, parse_price


def listing(title: str, price: float, seller: str = "Amazon.in") -> Listing:
    return Listing(title, price, "INR", f"₹{price}", seller, "https://example.com/item", 4.4)


def article(title: str, snippet: str = "") -> Article:
    return Article(title, "https://example.com/news", "The Hindu", "2 days ago", snippet)


def place() -> Place:
    return Place("Croma Indiranagar", 4.3, 800, "Indiranagar, Bengaluru", "https://example.com/map", "Electronics")


def page(title: str = "A long review") -> Page:
    return Page(title, "https://example.com/review", "A durable review of the product.")


class MoneyTests(unittest.TestCase):
    def test_indian_grouping(self) -> None:
        self.assertEqual(format_inr(999), "₹999")
        self.assertEqual(format_inr(1199), "₹1,199")
        self.assertEqual(format_inr(124900), "₹1,24,900")

    def test_parse_indian_price_label(self) -> None:
        self.assertEqual(parse_price("₹1,24,900"), 124900)
        self.assertIsNone(parse_price("Free"))


class PlanTests(unittest.TestCase):
    def test_plan_uses_four_serpapi_tools(self) -> None:
        plan = build_plan("boAt Airdopes 141", "Bengaluru, Karnataka, India")
        self.assertEqual(
            [step["tool"] for step in plan],
            ["shopping_search", "maps_search", "news_search", "web_search"],
        )
        self.assertTrue(all("boAt Airdopes 141" in step["query"] for step in plan))


class DecideTests(unittest.TestCase):
    def test_tight_market_buys(self) -> None:
        verdict = decide(
            product="boAt Airdopes 141",
            city="Bengaluru",
            budget=2000,
            listings=[listing("Airdopes", 1099), listing("Airdopes", 1199, "Flipkart")],
            places=[place()],
            articles=[article("boAt ships a new colorway")],
            pages=[page()],
            live_agents=4,
        )
        self.assertEqual(verdict.call, BUY)
        self.assertIsNone(verdict.dissent)
        self.assertTrue(verdict.action_url)

    def test_recall_holds(self) -> None:
        verdict = decide(
            product="Widget",
            city="Pune",
            budget=None,
            listings=[listing("Widget", 999), listing("Widget", 1040)],
            places=[],
            articles=[article("Widget recall after fire hazard reports", "safety notice")],
            pages=[page()],
            live_agents=4,
        )
        self.assertEqual(verdict.call, HOLD)
        self.assertEqual(verdict.rule, "recall")
        self.assertIn("https://example.com/news", verdict.action_url or "")

    def test_wide_spread_sends_you_to_the_street(self) -> None:
        verdict = decide(
            product="Headphones",
            city="Hyderabad",
            budget=30000,
            listings=[listing("Headphones", 18000), listing("Headphones", 26000)],
            places=[place()],
            articles=[article("A quiet week for headphones")],
            pages=[page()],
            live_agents=4,
        )
        self.assertEqual(verdict.call, SEE)
        self.assertEqual(verdict.rule, "spread-and-street")

    def test_over_budget_holds(self) -> None:
        verdict = decide(
            product="Phone",
            city="Mumbai",
            budget=20000,
            listings=[listing("Phone", 70000), listing("Phone", 72000)],
            places=[],
            articles=[],
            pages=[],
            live_agents=2,
        )
        self.assertEqual(verdict.call, HOLD)
        self.assertEqual(verdict.rule, "over-budget")

    def test_grouped_india_price_buys_and_keeps_dollar_deals_apart(self) -> None:
        headphones = Listing(
            "Sony WH-1000XM5 Wireless Noise Cancelling Headphones (Black)",
            19000,
            "INR",
            "₹19,000+",
            None,
            None,
            4.7,
            reviews=17000,
            multiple_sources=True,
            price_floor=True,
        )
        focused, set_aside = focus_listings(
            "Sony WH-1000XM5",
            [
                listing("WH-1000XM5 Soft Case", 83318, "Desertcart"),
                headphones,
                listing("Sony WH-1000XM5 Stone Series Skins", 2321, "Slickwraps"),
            ],
        )
        self.assertEqual(set_aside, 2)
        self.assertEqual(focused, [headphones])
        verdict = decide(
            product="Sony WH-1000XM5",
            city="Hyderabad",
            budget=25000,
            listings=focused,
            places=[place()],
            articles=[article("Sony WH-1000XM5 Headphones Hit 50% Discount, now $198")],
            pages=[page()],
            live_agents=4,
        )
        self.assertEqual(verdict.call, BUY)
        self.assertEqual(verdict.rule, "listed-from")
        self.assertIn("19000", verdict.headline.replace(",", "").replace("₹", ""))
        self.assertTrue(any("dollar" in reason.claim for reason in verdict.reasons))
        self.assertTrue(verdict.action_url)

    def test_maps_website_is_the_place_link(self) -> None:
        places = places_from(
            {
                "local_results": [
                    {
                        "title": "Sony Center",
                        "rating": 3.8,
                        "reviews": 514,
                        "address": "Abids, Hyderabad",
                        "type": "Electronics store",
                        "website": "https://shopatsc.com/",
                        "place_id": "ChIJtest",
                    }
                ]
            }
        )
        self.assertEqual(places[0].url, "https://shopatsc.com/")

    def test_shopping_parser_keeps_a_grouped_price(self) -> None:
        rows = listings_from(
            {
                "shopping_results": [
                    {
                        "title": "Sony WH-1000XM5 Wireless Noise Cancelling Headphones (Black)",
                        "price": "₹19,000+",
                        "extracted_price": 19000,
                        "multiple_sources": True,
                        "rating": 4.7,
                        "reviews": 17000,
                    }
                ]
            }
        )
        self.assertTrue(rows[0].multiple_sources)
        self.assertTrue(rows[0].price_floor)
        self.assertEqual(rows[0].price, 19000)

    def test_dollar_headline_forces_a_successor_search(self) -> None:
        follow = choose_followup(
            "Sony WH-1000XM5",
            [listing("Sony WH-1000XM5", 19000)],
            [article("Sony WH-1000XM5 drops to $198")],
        )
        self.assertTrue(follow.needed)
        self.assertEqual(follow.kind, "successor")
        self.assertEqual(follow.tool, "news_search")
        self.assertIn("successor", follow.query)

    def test_missing_india_price_forces_another_shopping_search(self) -> None:
        follow = choose_followup("Widget", [], [article("Widget review")])
        self.assertEqual(follow.kind, "india-price")
        self.assertEqual(follow.tool, "shopping_search")

    def test_agreeing_piles_skip_the_second_search(self) -> None:
        follow = choose_followup(
            "boAt Airdopes 141",
            [listing("boAt Airdopes 141", 1199)],
            [article("boAt ships a new colorway")],
        )
        self.assertFalse(follow.needed)

    def test_successor_followup_holds(self) -> None:
        verdict = decide(
            product="Sony WH-1000XM5",
            city="Hyderabad",
            budget=25000,
            listings=[listing("Sony WH-1000XM5", 19000)],
            places=[place()],
            articles=[article("Sony WH-1000XM5 drops to $198")],
            pages=[page()],
            live_agents=4,
            followup_articles=[article("Sony announces the WH-1000XM5 successor")],
            followup_status="done",
            followup_kind="successor",
        )
        self.assertEqual(verdict.call, HOLD)
        self.assertEqual(verdict.rule, "followup-successor")

    def test_buy_waits_until_the_successor_search_returns(self) -> None:
        headphones = Listing(
            "Sony WH-1000XM5",
            19000,
            "INR",
            "₹19,000+",
            None,
            None,
            4.7,
            reviews=17000,
            multiple_sources=True,
            price_floor=True,
        )
        verdict = decide(
            product="Sony WH-1000XM5",
            city="Hyderabad",
            budget=25000,
            listings=[headphones],
            places=[place()],
            articles=[article("Sony WH-1000XM5 drops to $198")],
            pages=[page()],
            live_agents=4,
            followup_status="error",
            followup_kind="successor",
        )
        self.assertEqual(verdict.provisional, BUY)
        self.assertEqual(verdict.call, SEE)
        self.assertEqual(verdict.rule, "followup-required")

    def test_a_higher_model_in_the_followup_holds(self) -> None:
        headphones = Listing(
            "Sony WH-1000XM5",
            19000,
            "INR",
            "₹19,000+",
            None,
            None,
            4.7,
            reviews=17000,
            multiple_sources=True,
            price_floor=True,
        )
        verdict = decide(
            product="Sony WH-1000XM5",
            city="Hyderabad",
            budget=25000,
            listings=[headphones],
            places=[place()],
            articles=[article("Sony WH-1000XM5 drops to $198")],
            pages=[page()],
            live_agents=4,
            followup_articles=[article("Sony WH-1000XM6 vs Sony WH-1000XM5: Should you upgrade?")],
            followup_status="done",
            followup_kind="successor",
        )
        self.assertEqual(verdict.call, HOLD)
        self.assertEqual(verdict.rule, "followup-successor")

    def test_a_different_models_headline_does_not_hold(self) -> None:
        headphones = Listing(
            "Sony WH-1000XM5",
            19000,
            "INR",
            "₹19,000+",
            None,
            None,
            4.7,
            reviews=17000,
            multiple_sources=True,
            price_floor=True,
        )
        verdict = decide(
            product="Sony WH-1000XM5",
            city="Hyderabad",
            budget=25000,
            listings=[headphones],
            places=[place()],
            articles=[article("Sony WH-1000XM5 drops to $198")],
            pages=[page()],
            live_agents=4,
            followup_articles=[
                article("Sony could revive its WH-1000XM4 headphones with a cheaper new model")
            ],
            followup_status="done",
            followup_kind="successor",
        )
        self.assertEqual(verdict.call, BUY)
        self.assertTrue(any("different model" in reason.claim for reason in verdict.reasons))

    def test_quiet_followup_lets_the_india_price_stand(self) -> None:
        headphones = Listing(
            "Sony WH-1000XM5",
            19000,
            "INR",
            "₹19,000+",
            None,
            None,
            4.7,
            reviews=17000,
            multiple_sources=True,
            price_floor=True,
        )
        verdict = decide(
            product="Sony WH-1000XM5",
            city="Hyderabad",
            budget=25000,
            listings=[headphones],
            places=[place()],
            articles=[article("Sony WH-1000XM5 drops to $198")],
            pages=[page()],
            live_agents=4,
            followup_articles=[article("XM5 stock is steady this week")],
            followup_status="done",
            followup_kind="successor",
        )
        self.assertEqual(verdict.call, BUY)
        self.assertTrue(any(reason.agent == "Second" for reason in verdict.reasons))

    def test_critic_vetoes_a_thin_buy(self) -> None:
        verdict = decide(
            product="Cable",
            city="Delhi",
            budget=1000,
            listings=[listing("Cable", 299), listing("Cable", 320)],
            places=[],
            articles=[],
            pages=[],
            live_agents=1,
        )
        self.assertEqual(verdict.provisional, BUY)
        self.assertEqual(verdict.call, SEE)
        self.assertIsNotNone(verdict.dissent)


if __name__ == "__main__":
    unittest.main()
