from django.urls import path
from .payment_return import PaymentReturnGrantView, PaymentReturnStatusView

from .payment_views import (
    PaymentInitializeView,
    PaymentVerifyView,
    PaystackWebhookView,
    OrderRepricingAcceptView,
)
from .operations_api import (
    OperationsActivityView,
    OperationsDashboardView,
    OperationsFiltersView,
    OperationsLoginView,
    OperationsLogoutView,
    OperationsMeView,
    OperationsHouseView,
    OperationsParticipantDetailView,
    OperationsParticipantListView,
    OperationsPaymentListView,
    OperationsRegistrationDetailView,
    OperationsRegistrationListView,
    OperationsReportView,
    operations_csrf,
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

from .participant_api import (
    portal_csrf, PortalOptionsView, PortalChallengeView, PortalVerifyView, PortalMeView,
    PortalLogoutView, PortalEnrollmentsView, PortalIDView, StaffEnrollmentView, StaffIDView,
)

urlpatterns = [
    path("participant/auth/csrf/", portal_csrf, name="participant-csrf"),
    path("participant/auth/options/", PortalOptionsView.as_view(), name="participant-options"),
    path("participant/auth/challenges/", PortalChallengeView.as_view(), name="participant-challenges"),
    path("participant/auth/verify/", PortalVerifyView.as_view(), name="participant-verify"),
    path("participant/auth/me/", PortalMeView.as_view(), name="participant-me"),
    path("participant/auth/logout/", PortalLogoutView.as_view(), name="participant-logout"),
    path("participant/enrollments/", PortalEnrollmentsView.as_view(), name="participant-enrollments"),
    path("participant/enrollments/<uuid:enrollment_id>/id/", PortalIDView.as_view(), name="participant-id"),
    path("operations/enrollments/", StaffEnrollmentView.as_view(), name="operations-enrollments"),
    path("operations/enrollments/<uuid:enrollment_id>/id/", StaffIDView.as_view(), name="operations-enrollment-id"),
    path("operations/auth/csrf/", operations_csrf, name="operations-csrf"),
    path(
        "operations/auth/login/",
        OperationsLoginView.as_view(),
        name="operations-login",
    ),
    path(
        "operations/auth/logout/",
        OperationsLogoutView.as_view(),
        name="operations-logout",
    ),
    path(
        "operations/auth/me/",
        OperationsMeView.as_view(),
        name="operations-me",
    ),
    path(
        "operations/dashboard/",
        OperationsDashboardView.as_view(),
        name="operations-dashboard",
    ),
    path(
        "operations/filters/",
        OperationsFiltersView.as_view(),
        name="operations-filters",
    ),
    path(
        "operations/registrations/",
        OperationsRegistrationListView.as_view(),
        name="operations-registrations",
    ),
    path(
        "operations/registrations/<uuid:public_id>/",
        OperationsRegistrationDetailView.as_view(),
        name="operations-registration-detail",
    ),
    path(
        "operations/participants/",
        OperationsParticipantListView.as_view(),
        name="operations-participants",
    ),
    path(
        "operations/participants/<uuid:participant_id>/",
        OperationsParticipantDetailView.as_view(),
        name="operations-participant-detail",
    ),
    path(
        "operations/payments/",
        OperationsPaymentListView.as_view(),
        name="operations-payments",
    ),
    path(
        "operations/houses/",
        OperationsHouseView.as_view(),
        name="operations-houses",
    ),
    path(
        "operations/activity/",
        OperationsActivityView.as_view(),
        name="operations-activity",
    ),
    path(
        "operations/reports/download/",
        OperationsReportView.as_view(),
        name="operations-report",
    ),
    path(
        "registration-options/",
        RegistrationOptionsView.as_view(),
        name="registration-options",
    ),
    path("orders/", RegistrationOrderCreateView.as_view(), name="order-create"),
    path("orders/<uuid:public_id>/payment-return-grant/", PaymentReturnGrantView.as_view(), name="payment-return-grant"),
    path("payments/return/", PaymentReturnStatusView.as_view(), name="payment-return-status"),
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


from .memory_views import MemoriesView, memory_image
urlpatterns += [
    path("memories/", MemoriesView.as_view(), name="memories"),
    path("memories/<int:pk>/image/", memory_image, name="memory-image"),
]

from .video_views import VideosView, VideoPlaybackView, video_thumbnail
urlpatterns += [
    path("videos/", VideosView.as_view(), name="videos"),
    path("videos/<int:pk>/playback/", VideoPlaybackView.as_view(), name="video-playback"),
    path("videos/<int:pk>/thumbnail/", video_thumbnail, name="video-thumbnail"),
]

from .showcase_views import ShowcaseView, showcase_image
urlpatterns += [
    path("showcase/", ShowcaseView.as_view(), name="showcase"),
    path("showcase/<str:kind>/<int:pk>/image/", showcase_image, name="showcase-image"),
]
