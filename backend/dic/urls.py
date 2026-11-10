from django.urls import path
from dic_finance.api import FinanceView
from dic_movement.api import ScanView, MovementView
from .assisted_registration import AssistedRegistrationPreparationView, AssistedBookingCreateView
from .payment_return import PaymentReturnGrantView, PaymentReturnStatusView
from .tutor_registration_api import TutorChallengeView, TutorVerifyView, TutorRedeemView
from .portal_continuation import PortalCapabilitiesView, PortalContinuationView

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
from .printing_api import PrintingDirectoryView, PrintingExportView, PrintingConfirmView
from .campsite_api import CampsiteOverviewView
from .reporting_api import ReportingView
from .checkin_api import CampCheckInView
from .scoring_api import HouseScoringView, HouseScoreReversalView
from .activity_scoring_api import ActivityScoringView, CamperScoringView
from .feedback_api import (CamperFeedbackOptionsView,CamperFeedbackSubmitView,CamperWelfareSubmitView,
    FeedbackFormOptionsView,IdentifiedFeedbackSubmitView,FeedbackSummaryView,WelfareReportsView,WelfareReportDetailView)

from .participant_api import (
    portal_csrf, PortalOptionsView, PortalChallengeView, PortalVerifyView, PortalMeView,
    PortalLogoutView, PortalEnrollmentsView, PortalIDView, StaffEnrollmentView, StaffIDView,
)

urlpatterns = [
    path('operations/reporting/', ReportingView.as_view(), name='operations-reporting'),
    path('tutor-registration/challenges/', TutorChallengeView.as_view(), name='tutor-challenge'),
    path('tutor-registration/verify/', TutorVerifyView.as_view(), name='tutor-verify'),
    path('tutor-registration/redeem/', TutorRedeemView.as_view(), name='tutor-redeem'),
    path('operations/assisted-registration/create/', AssistedBookingCreateView.as_view(), name='operations-assisted-registration-create'),
    path('operations/assisted-registration/', AssistedRegistrationPreparationView.as_view(), name='operations-assisted-registration-preparation'),
    path('operations/scan/', ScanView.as_view(), name='operations-scan'),
    path('operations/movements/', MovementView.as_view(), name='operations-movements'),
    path('operations/finance/', FinanceView.as_view(), name='operations-finance'),
    path('participant/scoring/', CamperScoringView.as_view(), name='camper-scoring'),
    path('operations/scoring/activities/', ActivityScoringView.as_view(), name='operations-activity-scoring'),
    path('participant/feedback/options/',CamperFeedbackOptionsView.as_view(),name='camper-feedback-options'),
    path('participant/feedback/',CamperFeedbackSubmitView.as_view(),name='camper-feedback'),
    path('participant/welfare/',CamperWelfareSubmitView.as_view(),name='camper-welfare'),
    path('operations/feedback/options/',FeedbackFormOptionsView.as_view(),name='feedback-form-options'),
    path('operations/feedback/submit/',IdentifiedFeedbackSubmitView.as_view(),name='identified-feedback'),
    path('operations/feedback/',FeedbackSummaryView.as_view(),name='feedback-summary'),
    path('operations/welfare/',WelfareReportsView.as_view(),name='welfare-reports'),
    path('operations/welfare/<uuid:report_id>/',WelfareReportDetailView.as_view(),name='welfare-detail'),
    path('operations/campsite/', CampsiteOverviewView.as_view(), name='operations-campsite'),
    path('operations/check-in/', CampCheckInView.as_view(), name='operations-check-in'),
    path('operations/scoring/', HouseScoringView.as_view(), name='operations-scoring'),
    path('operations/scoring/<int:entry_id>/reverse/', HouseScoreReversalView.as_view(), name='operations-score-reverse'),
    path('operations/id-printing/', PrintingDirectoryView.as_view(), name='id-printing'),
    path('operations/id-printing/export/', PrintingExportView.as_view(), name='id-printing-export'),
    path('operations/id-printing/<uuid:batch_id>/printed/', PrintingConfirmView.as_view(), name='id-printing-confirm'),
    path("participant/auth/csrf/", portal_csrf, name="participant-csrf"),
    path("participant/auth/options/", PortalOptionsView.as_view(), name="participant-options"),
    path('participant/auth/capabilities/', PortalCapabilitiesView.as_view(), name='participant-capabilities'),
    path('participant/auth/continue/', PortalContinuationView.as_view(), name='participant-continue'),
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


from .portal_account_api import (AccountStatusView, AccountActivateView, PasswordLoginView,
    PasswordResetView, AccountLinkBookingView, GoogleStartView, GoogleCallbackView, GoogleUnlinkView, EmailVerifyView, EmailResendView)
urlpatterns += [
    path('participant/auth/email/verify/', EmailVerifyView.as_view(), name='portal-email-verify'),
    path('participant/auth/email/resend/', EmailResendView.as_view(), name='portal-email-resend'),
    path('participant/auth/account/', AccountStatusView.as_view(), name='portal-account'),
    path('participant/auth/account/activate/', AccountActivateView.as_view(), name='portal-account-activate'),
    path('participant/auth/account/link-booking/', AccountLinkBookingView.as_view(), name='portal-account-link-booking'),
    path('participant/auth/password/login/', PasswordLoginView.as_view(), name='portal-password-login'),
    path('participant/auth/password/reset/', PasswordResetView.as_view(), name='portal-password-reset'),
    path('participant/auth/google/start/', GoogleStartView.as_view(), name='portal-google-start'),
    path('participant/auth/google/callback/', GoogleCallbackView.as_view(), name='portal-google-callback'),
    path('participant/auth/google/unlink/', GoogleUnlinkView.as_view(), name='portal-google-unlink'),
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

from .promo_views import DICEditorialView, editorial_image, promo_stream
urlpatterns += [
    path('editorial/', DICEditorialView.as_view(), name='dic-editorial'),
    path('promotions/<int:pk>/video/', promo_stream, name='promo-stream'),
    path('promotions/<int:pk>/poster/', editorial_image, {'kind': 'poster'}, name='promo-poster'),
    path('flyer/<int:pk>/', editorial_image, {'kind': 'flyer'}, name='official-flyer'),
]

from .identity_views import card_view, verify_view
from .timetable_api import ParticipantTimetableView, OperationsTimetableView
from .launch_api import CampUpdatesView
from .launch_operations_api import (LaunchOptionsView, OperationsClassesView, OperationsClassDetailView,
    OperationsAssignmentsView, OperationsAnnouncementsView, OperationsAnnouncementDetailView,
    OperationsAnnouncementPublicationView, OperationsLaunchHistoryView)
from .local_diagnostics import local_database_identity
from .participant_api import PortalCardView
urlpatterns += [
    path('operations/camp-management/options/', LaunchOptionsView.as_view(), name='operations-launch-options'),
    path('operations/classes/', OperationsClassesView.as_view(), name='operations-classes'),
    path('operations/classes/<int:class_id>/', OperationsClassDetailView.as_view(), name='operations-class-detail'),
    path('operations/class-assignments/', OperationsAssignmentsView.as_view(), name='operations-class-assignments'),
    path('operations/announcements/', OperationsAnnouncementsView.as_view(), name='operations-announcements'),
    path('operations/announcements/<int:announcement_id>/', OperationsAnnouncementDetailView.as_view(), name='operations-announcement-detail'),
    path('operations/announcements/<int:announcement_id>/publication/', OperationsAnnouncementPublicationView.as_view(), name='operations-announcement-publication'),
    path('operations/camp-management/<str:domain>/history/', OperationsLaunchHistoryView.as_view(), name='operations-launch-history'),
    path('participant/enrollments/<uuid:enrollment_id>/card/', PortalCardView.as_view(), name='participant-card'),
    path('participant/timetables/', ParticipantTimetableView.as_view(), name='participant-timetables'),
    path('participant/camp-updates/', CampUpdatesView.as_view(), name='participant-camp-updates'),
    path('operations/timetables/', OperationsTimetableView.as_view(), name='operations-timetables'),
    path('local-preview/database/', local_database_identity, name='local-preview-database'),
    path('ids/cards/<uuid:enrollment_id>/', card_view, name='id-card'),
    path('ids/verify/', verify_view, name='verify-id'),
]
