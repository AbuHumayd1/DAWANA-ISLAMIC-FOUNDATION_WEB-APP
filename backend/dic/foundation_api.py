"""Foundation enquiries and test-only donations, isolated from DIC order settlement."""
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse
from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError, NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView
from .models import ContactEnquiry, FoundationDonation
from .payments import PaystackClient, PaystackConfigurationError, paystack_secret_key, verify_webhook_request


def unavailable(message):
    error=APIException(message); error.status_code=503; raise error


def storage(model):
    if model._meta.db_table not in connection.introspection.table_names():
        unavailable('This service awaits approved setup. Please try again later.')


def digest(value): return hmac.new(settings.SECRET_KEY.encode(),value.encode(),hashlib.sha256).hexdigest()


class PublicThrottle(SimpleRateThrottle):
    rate='20/hour'
    scope='foundation_public'
    def get_cache_key(self,request,view):
        return 'foundation:'+self.scope+':'+digest(request.META.get('REMOTE_ADDR','unknown'))


class WebhookThrottle(PublicThrottle):
    rate='120/minute'
    scope='foundation_webhook'


class OptionsThrottle(PublicThrottle):
    rate='300/hour'
    scope='foundation_options'


class PublicAPI(APIView):
    authentication_classes=()
    permission_classes=(AllowAny,)
    throttle_classes=(PublicThrottle,)
    @method_decorator(csrf_protect)
    def dispatch(self,*args,**kwargs): return super().dispatch(*args,**kwargs)
    def finalize_response(self,*args,**kwargs):
        response=super().finalize_response(*args,**kwargs)
        response['Cache-Control']='no-store'; response['X-Content-Type-Options']='nosniff'
        return response


@ensure_csrf_cookie
def public_csrf(request):
    response=JsonResponse({'csrfToken':get_token(request)})
    response['Cache-Control']='no-store'
    return response


def official_channels():
    source=json.loads((Path(__file__).parent/'data/foundation_contact.json').read_text(encoding='utf-8'))
    if not source.get('verified'): return {}
    channels={}
    use_override=getattr(settings,'FOUNDATION_CONTACT_VERIFIED',False)
    email=getattr(settings,'FOUNDATION_CONTACT_EMAIL','') if use_override else source.get('email','')
    if email:
        try: channels['email']=serializers.EmailField().run_validation(email)
        except serializers.ValidationError: pass
    for key in ('phone','whatsapp'):
        value=getattr(settings,'FOUNDATION_CONTACT_'+key.upper(),'') if use_override else ''
        if re.fullmatch(r'\+[1-9][0-9]{7,14}',value): channels[key]=value
    channels['phones']=[v for v in source.get('phones',[]) if re.fullmatch(r'\+[1-9][0-9]{7,14}',v)]
    address=getattr(settings,'FOUNDATION_CONTACT_ADDRESS','') if use_override else ''
    if address and len(address)<=500: channels['address']=address
    return channels


def donation_limits():
    try:
        minimum=Decimal(str(getattr(settings,'FOUNDATION_DONATION_MIN_NGN','')))
        maximum=Decimal(str(getattr(settings,'FOUNDATION_DONATION_MAX_NGN','')))
        if not minimum.is_finite() or not maximum.is_finite() or minimum<=0 or maximum<minimum:
            return None
        if any(v*100 != (v*100).to_integral_value() for v in (minimum,maximum)) or maximum*100>9223372036854775807:
            return None
        return minimum,maximum
    except (InvalidOperation,ValueError,TypeError): return None


def donation_ready():
    if not (getattr(settings,'FOUNDATION_DONATIONS_ENABLED',False) and donation_limits()
            and getattr(settings,'FOUNDATION_DONATION_CURRENCY','')=='NGN'):
        return False
    try:
        paystack_secret_key()
    except PaystackConfigurationError:
        return False
    return True


def require_donations():
    if not donation_ready(): unavailable('Donations are not enabled. No payment has been initiated.')
    storage(FoundationDonation)


class FoundationOptions(PublicAPI):
    throttle_classes=(OptionsThrottle,)
    def get(self,request):
        limits=donation_limits()
        return Response(dict(channels=official_channels(),contact_enabled=bool(getattr(settings,'FOUNDATION_CONTACT_FORM_ENABLED',False)),
            donations_enabled=donation_ready(),currency='NGN',minimum=str(limits[0]) if limits else None,
            maximum=str(limits[1]) if limits else None,payment_mode='test'))


class EnquiryInput(serializers.Serializer):
    name=serializers.CharField(max_length=120)
    email=serializers.EmailField(max_length=254)
    subject=serializers.CharField(max_length=200)
    message=serializers.CharField(min_length=10,max_length=5000)
    website=serializers.CharField(required=False,allow_blank=True,max_length=200)


class EnquiryView(PublicAPI):
    def post(self,request):
        if not getattr(settings,'FOUNDATION_CONTACT_FORM_ENABLED',False): unavailable('The enquiry inbox is not enabled yet.')
        form=EnquiryInput(data=request.data); form.is_valid(raise_exception=True)
        data=dict(form.validated_data)
        if data.pop('website',''): return Response({'received':True},status=202)
        storage(ContactEnquiry)
        key='enquiry_duplicate:'+digest(json.dumps(data,sort_keys=True))
        if not cache.add(key,True,timeout=300): return Response({'received':True},status=202)
        try: ContactEnquiry.objects.create(**data)
        except Exception:
            cache.delete(key)
            raise
        return Response({'received':True},status=202)


class DonationInput(serializers.Serializer):
    request_id=serializers.UUIDField()
    access_token=serializers.RegexField(r'^[A-Za-z0-9_-]{43,128}$')
    email=serializers.EmailField(max_length=254)
    amount=serializers.DecimalField(max_digits=19,decimal_places=2,min_value=Decimal('0.01'),max_value=Decimal('92233720368547758.07'))


def event(row,name):
    row.audit=(row.audit+[{'event':name,'at':timezone.now().isoformat()}])[-200:]


def donation_payload(row):
    return dict(reference=row.reference,status=row.status,amount_kobo=row.amount_kobo,currency=row.currency,
        authorization_url=row.authorization_url if row.status in ('pending','initializing') else '',payment_mode='test')


def valid_checkout(url):
    try:
        parsed=urlparse(url)
        return parsed.scheme=='https' and parsed.hostname=='checkout.paystack.com' and not parsed.username and not parsed.password and parsed.port in (None,443)
    except (ValueError,TypeError): return False


class DonationCreate(PublicAPI):
    def post(self,request):
        require_donations()
        form=DonationInput(data=request.data); form.is_valid(raise_exception=True)
        data=form.validated_data; limits=donation_limits()
        if not limits[0]<=data['amount']<=limits[1]: raise ValidationError('Choose an amount within the approved donation limits.')
        amount=int(data['amount']*100)
        fingerprint=digest(json.dumps([str(data['amount']),data['email'].lower()]))
        with transaction.atomic():
            row,_=FoundationDonation.objects.get_or_create(request_id=data['request_id'],defaults=dict(
                reference='foundation-donation-'+uuid.uuid4().hex,fingerprint=fingerprint,
                provider_mode=settings.PAYSTACK_MODE,
                token_digest=digest(data['access_token']),email=data['email'],amount_kobo=amount))
            row=FoundationDonation.objects.select_for_update().get(pk=row.pk)
            if not hmac.compare_digest(row.token_digest,digest(data['access_token'])) or row.fingerprint!=fingerprint:
                raise ValidationError('Donation request conflicts with an existing request.')
            if row.provider_mode != settings.PAYSTACK_MODE:
                raise ValidationError('Donation environment mismatch. Authorized reconciliation is required.')
            if row.status!='created': return Response(donation_payload(row))
            row.status='initializing'; event(row,'initialization_requested'); row.save()
        try:
            provider=PaystackClient().initialize_transaction(email=row.email,amount_kobo=row.amount_kobo,
                reference=row.reference,metadata={'purpose':'foundation_donation'})
            url=provider.get('authorization_url','')
            if provider.get('reference')!=row.reference or not valid_checkout(url): raise ValueError('Untrusted provider response')
        except Exception:
            with transaction.atomic():
                row=FoundationDonation.objects.select_for_update().get(pk=row.pk)
                if row.status=='initializing':
                    row.status='review'; event(row,'initialization_uncertain'); row.save()
            unavailable('Payment initialization could not be confirmed. Keep this request and check its status; do not pay again.')
        with transaction.atomic():
            row=FoundationDonation.objects.select_for_update().get(pk=row.pk)
            if row.status=='initializing':
                row.status='pending'; row.authorization_url=url; event(row,'initialized'); row.save()
        return Response(donation_payload(row),status=201)


def verified_status(row,data):
    if (data.get('reference')!=row.reference or type(data.get('amount')) is not int
            or data.get('amount')!=row.amount_kobo or data.get('currency')!='NGN'
            or row.provider_mode not in ('test','live')
            or data.get('domain') != row.provider_mode or row.provider_mode != settings.PAYSTACK_MODE):
        return 'review'
    return {'success':'successful','failed':'failed','abandoned':'abandoned','pending':'pending','ongoing':'pending','processing':'pending'}.get(data.get('status'),'review')


@transaction.atomic
def settle_donation(reference,data):
    row=FoundationDonation.objects.select_for_update().get(reference=reference)
    if row.status=='successful': return row
    row.status=verified_status(row,data); event(row,'verified_'+row.status)
    row.audit[-1]['proof']={
        'amount_kobo':data.get('amount') if type(data.get('amount')) is int else None,
        'currency':str(data.get('currency',''))[:12], 'domain':str(data.get('domain',''))[:12],
        'status':str(data.get('status',''))[:24]}
    row.save()
    return row


class DonationStatus(PublicAPI):
    def authorized(self,request,reference):
        require_donations()
        token=request.headers.get('X-Donation-Token','')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43,128}',token): raise NotFound('Donation request unavailable.')
        row=FoundationDonation.objects.filter(reference=reference,token_digest=digest(token)).first()
        if not row: raise NotFound('Donation request unavailable.')
        if row.provider_mode != settings.PAYSTACK_MODE:
            raise ValidationError('Donation environment mismatch. Authorized reconciliation is required.')
        return row
    def get(self,request,reference): return Response(donation_payload(self.authorized(request,reference)))
    def post(self,request,reference):
        row=self.authorized(request,reference)
        if row.status!='successful':
            try: data=PaystackClient().verify_transaction(row.reference)
            except Exception: unavailable('Verification is temporarily unavailable; the donation is not confirmed.')
            row=settle_donation(row.reference,data)
        return Response(donation_payload(row))


class DonationWebhook(APIView):
    authentication_classes=()
    permission_classes=(AllowAny,)
    throttle_classes=(WebhookThrottle,)
    def post(self,request):
        require_donations()
        if len(request.body)>65536: raise ValidationError('Webhook rejected.')
        client=PaystackClient()
        if not verify_webhook_request(request.body,request.headers,client.secret_key): raise PermissionDenied('Webhook signature rejected.')
        payload=request.data
        data=payload.get('data',{}) if isinstance(payload,dict) else {}
        reference=data.get('reference','') if isinstance(data,dict) else ''
        if not isinstance(reference,str) or not reference.startswith('foundation-donation-') or not FoundationDonation.objects.filter(reference=reference).exists(): return Response({'received':True})
        try: proof=client.verify_transaction(reference)
        except Exception: unavailable('Webhook verification is temporarily unavailable.')
        settle_donation(reference,proof)
        return Response({'received':True})
