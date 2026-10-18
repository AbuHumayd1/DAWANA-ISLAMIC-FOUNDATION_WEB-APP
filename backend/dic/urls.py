from django.urls import path

from .payment_views import (
    PaymentInitializeView,
    PaymentVerifyView,
    PaystackWebhookView,
    OrderRepricingAcceptView,
)
from .recovery_views import (
    RecoveryChallengeView,
    RecoveryChannelsView,
    RecoveryOrdersView,
    RecoveryResendView,
    RecoveryRestoreOrderView,
    RecoveryVerifyView,
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
        "orders/<uuid:public_id>/pricing/accept/",
        OrderRepricingAcceptView.as_view(),
        name="pricing-accept",
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
    path(
        "recovery/channels/",
        RecoveryChannelsView.as_view(),
        name="recovery-channels",
    ),
    path(
        "recovery/challenges/",
        RecoveryChallengeView.as_view(),
        name="recovery-challenge",
    ),
    path(
        "recovery/challenges/<uuid:challenge_id>/resend/",
        RecoveryResendView.as_view(),
        name="recovery-resend",
    ),
    path(
        "recovery/challenges/<uuid:challenge_id>/verify/",
        RecoveryVerifyView.as_view(),
        name="recovery-verify",
    ),
    path(
        "recovery/orders/",
        RecoveryOrdersView.as_view(),
        name="recovery-orders",
    ),
    path(
        "recovery/orders/<uuid:public_id>/restore/",
        RecoveryRestoreOrderView.as_view(),
        name="recovery-restore-order",
    ),
]
