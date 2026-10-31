from rest_framework.routers import DefaultRouter

from apps.accounts.views import UserViewSet

from .views import (
    BillingRunViewSet,
    CustomerViewSet,
    DiscountRuleViewSet,
    InvoiceViewSet,
    PaymentViewSet,
    PlanViewSet,
    ProductViewSet,
    QuotationTemplateViewSet,
    SubscriptionViewSet,
    TaxRuleViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("customers", CustomerViewSet, basename="customer")
router.register("products", ProductViewSet, basename="product")
router.register("plans", PlanViewSet, basename="plan")
router.register("tax-rules", TaxRuleViewSet, basename="tax-rule")
router.register("quotation-templates", QuotationTemplateViewSet, basename="quotation-template")
router.register("subscriptions", SubscriptionViewSet, basename="subscription")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("payments", PaymentViewSet, basename="payment")
router.register("discount-rules", DiscountRuleViewSet, basename="discount-rule")
router.register("billing-runs", BillingRunViewSet, basename="billing-run")

urlpatterns = router.urls
