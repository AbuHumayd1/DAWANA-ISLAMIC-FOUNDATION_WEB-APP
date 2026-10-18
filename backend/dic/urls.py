from django.urls import path

from .payment_views import (
    PaymentInitializeView,
    PaymentVerifyView,
    PaystackWebhookView,
)
from .views import (
    RegistrationOptionsView,
    RegistrationOrderCreateView,
    RegistrationOrderDetailView,
)


app_name = "dic"

urlpatterns = [
    path(
        "registration-options/",
        RegistrationOptionsView.as_view(),
        name="registration-options",
    ),
    path("orders/", RegistrationOrderCreateView.as_view(), name="order-create"),
    path(
        "orders/<uuid:public_id>/",
        RegistrationOrderDetailView.as_view(),
        name="order-detail",
    ),
    path(
        "orders/<uuid:public_id>/payments/initialize/",
        PaymentInitializeView.as_view(),
        name="payment-initialize",
    ),
    path(
        "orders/<uuid:public_id>/payments/<str:reference>/verify/",
        PaymentVerifyView.as_view(),
        name="payment-verify",
    ),
    path(
        "payments/paystack/webhook/",
        PaystackWebhookView.as_view(),
        name="paystack-webhook",
    ),
]
