"""Private direct multipart uploads; never publish or accept arbitrary object keys."""
import math
import uuid
from pathlib import Path
from django.core import signing
from django.core.exceptions import ValidationError as ModelValidationError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.forms import modelform_factory
from botocore.exceptions import BotoCoreError, ClientError
from rest_framework.exceptions import ValidationError, PermissionDenied, APIException
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .studio_api import StudioView, upload_enabled
from .recording_storage import recording_storage, validate_video, MAX_RECORDING
from .memory_models import CampVideo
from .models import DICAdminAuditEvent

PART = 8 * 1024 * 1024
SALT = 'dic.studio.video.multipart.v1'


class TransferUnavailable(APIException):
    status_code = 503
    default_detail = 'Video storage is temporarily unavailable. Retry the same upload.'


class StudioVideoTransfer(StudioView):
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def post(self, request):
        if not request.user.has_perm('dic.add_campvideo'):
            raise PermissionDenied('Video upload access required.')
        if not upload_enabled():
            raise TransferUnavailable()
        client = recording_storage._client()
        bucket = recording_storage._bucket()
        action = request.data.get('action')
        try:
            if action == 'start':
                size = request.data.get('size')
                suffix = Path(str(request.data.get('name', ''))).suffix.lower()
                if type(size) is not int or not 0 < size <= MAX_RECORDING or suffix not in ('.mp4', '.webm'):
                    raise ValidationError('Choose an MP4 or WebM video of at most 200 MB.')
                key = 'camp-recordings/' + uuid.uuid4().hex + suffix
                mime = 'video/mp4' if suffix == '.mp4' else 'video/webm'
                upload = client.create_multipart_upload(Bucket=bucket, Key=key, ContentType=mime)
                ticket = signing.dumps({'user': request.user.pk, 'key': key, 'upload': upload['UploadId'], 'size': size}, salt=SALT)
                return self.nocache({'ticket': ticket, 'part_size': PART})
            try:
                data = signing.loads(request.data.get('ticket', ''), salt=SALT, max_age=86400)
                if data['user'] != request.user.pk:
                    raise ValueError()
            except (signing.BadSignature, ValueError, TypeError, KeyError):
                raise ValidationError('Upload session expired or invalid. Start a new upload.')
            key, upload, size = data['key'], data['upload'], data['size']
            params = {'Bucket': bucket, 'Key': key, 'UploadId': upload}
            count = math.ceil(size / PART)
            if action == 'part':
                number = request.data.get('number')
                if type(number) is not int or not 1 <= number <= count:
                    raise ValidationError('Invalid upload part.')
                length = min(PART, size - (number - 1) * PART)
                url = client.generate_presigned_url('upload_part', Params={**params, 'PartNumber': number, 'ContentLength': length}, ExpiresIn=900)
                return self.nocache({'url': url})
            if action != 'finish':
                raise ValidationError('Unknown video transfer action.')
            # Serialize finalization for this staff identity, including a lost response.
            with transaction.atomic():
                get_user_model().objects.select_for_update().get(pk=request.user.pk)
                existing = CampVideo.objects.filter(recording_file=key).first()
                if existing:
                    return self.nocache({'id': existing.pk, 'state': existing.state})
                Form = modelform_factory(CampVideo, fields=('edition','caption','alt_text','thumbnail','lecturer','description'))
                form = Form(request.data, request.FILES)
                if not form.is_valid():
                    # The model clean requires a recording; validate form fields separately below.
                    errors = form.errors.as_data()
                    if set(errors) - {'__all__'} or any('Choose one approved hosted video link' not in e.message for e in errors.get('__all__', [])):
                        raise ValidationError({k: list(v) for k,v in form.errors.items()})
                try:
                    head = client.head_object(Bucket=bucket, Key=key)
                except ClientError as error:
                    if error.response.get('Error', {}).get('Code') not in ('404','NoSuchKey','NotFound'):
                        raise
                    parts = client.list_parts(**params).get('Parts', [])
                    if len(parts) != count or any(p['PartNumber'] != i or p['Size'] != min(PART,size-(i-1)*PART) for i,p in enumerate(parts,1)):
                        raise ValidationError('Video transfer incomplete. Retry the same upload.')
                    client.complete_multipart_upload(**params, MultipartUpload={'Parts':[{'PartNumber':p['PartNumber'],'ETag':p['ETag']} for p in parts]})
                    head = client.head_object(Bucket=bucket, Key=key)
                if head['ContentLength'] != size:
                    raise ValidationError('Uploaded video size does not match the selected file.')
                with recording_storage.open(key) as media:
                    validate_video(media)
                item = form.instance
                item.recording_file = key
                item.state = 'draft'
                item.save(actor=request.user)
                DICAdminAuditEvent.objects.create(actor=request.user, action='studio_media_draft_uploaded', target_type='CampVideo', target_id=str(item.pk), details={'library':'videos','direct':True})
                return self.nocache({'id':item.pk,'state':item.state},status=201)
        except ModelValidationError as error:
            raise ValidationError(error.messages) from error
        except (BotoCoreError, ClientError):
            raise TransferUnavailable() from None
