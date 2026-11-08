"""A small starting test suite for the order desk."""

from pathlib import Path
import tempfile
import unittest

from supplydesk.service import OrderService


class OrderSmokeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def test_regular_pickup_quote(self):
        quote = self.service.quote("regular", [{"product_id": "notebook", "quantity": 2}])
        self.assertEqual(quote["subtotal_cents"], 1000)
        self.assertEqual(quote["discount_cents"], 0)
        self.assertEqual(quote["delivery_cents"], 0)
        self.assertEqual(quote["total_cents"], 1000)

    def test_student_delivery_quote(self):
        quote = self.service.quote("student", [{"product_id": "hoodie", "quantity": 2}], "delivery")
        self.assertEqual(quote["discount_cents"], 800)
        self.assertEqual(quote["delivery_cents"], 600)
        self.assertEqual(quote["total_cents"], 7800)

    def test_order_can_be_reopened(self):
        order = self.service.place_order("regular", [{"product_id": "mug", "quantity": 1}])
        self.assertEqual(order["order_id"], "ORD-0001")        
        self.assertEqual(order["status"], "placed")
        self.assertEqual(OrderService(self.path).get_order(order["order_id"]), order)

    def test_cancel_order_restores_stock(self):
        before = self.service.catalog()
        order = self.service.place_order("regular", [{"product_id": "pen-pack", "quantity": 2}])
        cancelled = self.service.cancel_order(order["order_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(self.service.catalog(), before)


    # Additional behavioural tests for the Task 2 testing safety net.
    def test_successful_order_records_total_and_reduces_stock(self):
        before = {p["product_id"]: p["stock"] for p in self.service.catalog()}

        order = self.service.place_order(
            "regular", [{"product_id": "notebook", "quantity": 2}]
        )

        self.assertEqual(order["total_cents"], 1000)
        self.assertEqual(order["status"], "placed")
        self.assertEqual(order["order_id"], "ORD-0001")
        after = {p["product_id"]: p["stock"] for p in self.service.catalog()}
        self.assertEqual(after["notebook"], before["notebook"] - 2)
        self.assertEqual(after["mug"], before["mug"])

    def test_student_discount_applies_at_exactly_fifty_dollars(self):
        # Ten notebooks cost exactly $50.00; the specification says "at least".
        quote = self.service.quote(
            "student", [{"product_id": "notebook", "quantity": 10}]
        )

        self.assertEqual(quote["subtotal_cents"], 5000)
        self.assertEqual(quote["discount_cents"], 500)
        self.assertEqual(quote["total_cents"], 4500)

    def test_quantity_of_one_is_valid_boundary(self):
        quote = self.service.quote(
            "regular", [{"product_id": "notebook", "quantity": 1}]
        )
        self.assertEqual(quote["items"][0]["quantity"], 1)
        self.assertEqual(quote["total_cents"], 500)

    def test_duplicate_product_lines_cannot_exceed_combined_stock(self):
        # Hoodie stock starts at five. Each line is individually valid, but
        # together they request six units and must be rejected.
        with self.assertRaisesRegex(ValueError, "Not enough stock"):
            self.service.place_order(
                "regular",
                [
                    {"product_id": "hoodie", "quantity": 3},
                    {"product_id": "hoodie", "quantity": 3},
                ],
            )

        self.assertEqual(self.service.catalog()[2]["stock"], 5)
        self.assertEqual(self.service.list_orders(), [])
        next_order = self.service.place_order(
            "regular", [{"product_id": "mug", "quantity": 1}]
        )
        self.assertEqual(next_order["order_id"], "ORD-0001")

    def test_invalid_requests_raise_value_error_without_changing_state(self):
        invalid_requests = [
            ("regular", [{"product_id": "missing", "quantity": 1}], "pickup"),
            ("regular", [{"product_id": "notebook", "quantity": 0}], "pickup"),
            ("regular", [{"product_id": "notebook", "quantity": True}], "pickup"),
            ("guest", [{"product_id": "notebook", "quantity": 1}], "pickup"),
            ("regular", [{"product_id": "notebook", "quantity": 1}], "drone"),
            ("regular", [], "pickup"),
        ]
        for customer_type, items, fulfillment in invalid_requests:
            with self.subTest(customer_type=customer_type, items=items, fulfillment=fulfillment):
                before_catalog = self.service.catalog()
                before_orders = self.service.list_orders()
                with self.assertRaises(ValueError):
                    self.service.place_order(customer_type, items, fulfillment)
                self.assertEqual(self.service.catalog(), before_catalog)
                self.assertEqual(self.service.list_orders(), before_orders)

    def test_quote_does_not_create_file_or_change_stock_or_order_history(self):
        before_catalog = self.service.catalog()

        quote = self.service.quote(
            "regular", [{"product_id": "mug", "quantity": 2}]
        )

        self.assertEqual(quote["total_cents"], 3000)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.service.catalog(), before_catalog)
        self.assertEqual(self.service.list_orders(), [])

    def test_quote_and_placement_have_matching_pricing_and_item_details(self):
        items = [{"product_id": "hoodie", "quantity": 2}]
        quote = self.service.quote("student", items, "delivery")
        order = self.service.place_order("student", items, "delivery")

        for key in (
            "customer_type", "fulfillment", "items", "subtotal_cents",
            "discount_cents", "delivery_cents", "total_cents",
        ):
            self.assertEqual(order[key], quote[key])

    def test_cancelling_an_already_cancelled_order_does_not_restore_stock_twice(self):
        order = self.service.place_order(
            "regular", [{"product_id": "pen-pack", "quantity": 2}]
        )
        self.service.cancel_order(order["order_id"])
        stock_after_first_cancellation = self.service.catalog()[1]["stock"]

        second_result = self.service.cancel_order(order["order_id"])

        self.assertEqual(second_result["status"], "cancelled")
        self.assertEqual(
            self.service.catalog()[1]["stock"], stock_after_first_cancellation
        )
        self.assertEqual(len(self.service.list_orders()), 1)


if __name__ == "__main__":
    unittest.main()

