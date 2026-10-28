from django.urls import path
from .foundation_api import public_csrf, FoundationOptions, EnquiryView, DonationCreate, DonationStatus, DonationWebhook

urlpatterns=[path('csrf/',public_csrf),path('options/',FoundationOptions.as_view()),
    path('contact/',EnquiryView.as_view()),path('donations/',DonationCreate.as_view()),
    path('donations/webhook/',DonationWebhook.as_view()),path('donations/<str:reference>/',DonationStatus.as_view())]
