"""Private direct multipart uploads; never publish or accept arbitrary object keys."""
import math
import subprocess
import tempfile
import os
from django.conf import settings
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
from .promo_models import PromoVideo
from .promo_storage import validate_mp4, private_promo_storage
from .models import DICAdminAuditEvent

PART = 8 * 1024 * 1024
SALT = 'dic.studio.video.multipart.v1'


class TransferUnavailable(APIException):
    status_code = 503
    default_detail = 'Video storage is temporarily unavailable. Retry the same upload.'


class StudioVideoTransfer(StudioView):
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def post(self, request):
        kind = request.data.get('collection', 'videos')
        if kind not in ('videos','promotions'):
            raise ValidationError('Unknown video collection.')
        model, field, storage = (CampVideo, 'recording_file', recording_storage) if kind == 'videos' else (PromoVideo, 'video', private_promo_storage)
        if not request.user.has_perm('dic.add_' + model._meta.model_name):
            raise PermissionDenied('Video upload access required.')
        if not upload_enabled():
            raise TransferUnavailable()
        client = storage._client()
        bucket = storage._bucket()
        action = request.data.get('action')
        try:
            if action == 'start':
                size = request.data.get('size')
                suffix = Path(str(request.data.get('name', ''))).suffix.lower()
                if type(size) is not int or not 0 < size <= MAX_RECORDING or suffix not in (('.mp4', '.webm', '.mov') if kind == 'videos' else ('.mp4', '.mov')):
                    raise ValidationError('Choose a supported video of at most 1 GB.')
                key = ('camp-recordings/' if kind == 'videos' else 'memories/promos/') + uuid.uuid4().hex + suffix
                mime = {'.mp4':'video/mp4','.webm':'video/webm','.mov':'video/quicktime'}[suffix]
                upload = client.create_multipart_upload(Bucket=bucket, Key=key, ContentType=mime)
                ticket = signing.dumps({'user': request.user.pk, 'key': key, 'upload': upload['UploadId'], 'size': size, 'kind': kind}, salt=SALT)
                return self.nocache({'ticket': ticket, 'part_size': PART})
            try:
                data = signing.loads(request.data.get('ticket', ''), salt=SALT, max_age=86400)
                if data['user'] != request.user.pk or data.get('kind') != kind:
                    raise ValueError()
            except (signing.BadSignature, ValueError, TypeError, KeyError):
                raise ValidationError('Upload session expired or invalid. Start a new upload.')
            key, upload, size = data['key'], data['upload'], data['size']
            params = {'Bucket': bucket, 'Key': key, 'UploadId': upload}
            count = math.ceil(size / PART)
            if action == 'status':
                try:
                    head = client.head_object(Bucket=bucket, Key=key)
                    if head['ContentLength'] != size:
                        raise ValidationError('Uploaded video size does not match.')
                    return self.nocache({'parts': list(range(1, count+1))})
                except ClientError as error:
                    if error.response.get('Error', {}).get('Code') not in ('404','NoSuchKey','NotFound'):
                        raise
                parts = client.list_parts(**params).get('Parts', [])
                return self.nocache({'parts': [p['PartNumber'] for p in parts if 1 <= p['PartNumber'] <= count and p['Size'] == min(PART,size-(p['PartNumber']-1)*PART)]})
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
                existing = model.objects.filter(**{field+'__in': [key, key[:-4]+'.mp4'] if key.endswith('.mov') else [key]}).first()
                if existing:
                    return self.nocache({'id': existing.pk, 'state': existing.state})
                fields = ('edition','caption','alt_text','thumbnail','lecturer','description') if kind == 'videos' else ('edition','source_edition','kind','title','description','poster','alt_text')
                Form = modelform_factory(model, fields=fields)
                form = Form(request.data, request.FILES, instance=model(**{field:key}))
                if not form.is_valid():
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
                with storage.open(key) as media:
                    if kind == 'videos':
                        validate_video(media)
                    else:
                        validate_mp4(media)
                # MOV containers must be remuxed to MP4 for cross-browser delivery.
                # Compatible H.264/AAC streams are copied, not re-encoded.
                if key.endswith('.mov'):
                    converted = key[:-4] + '.mp4'
                    with tempfile.TemporaryDirectory() as directory:
                        source = os.path.join(directory, 'source.mov')
                        output = os.path.join(directory, 'output.mp4')
                        with storage.open(key) as media, open(source, 'wb') as target:
                            for chunk in media.chunks(): target.write(chunk)
                        try:
                            subprocess.run([getattr(settings,'DIC_FFMPEG_BINARY','ffmpeg'), '-nostdin','-v','error','-protocol_whitelist','file','-i',source,'-map','0:v:0','-map','0:a:0?','-c','copy','-movflags','+faststart',output], check=True, timeout=120, capture_output=True)
                        except (OSError, subprocess.SubprocessError):
                            raise ValidationError('This MOV cannot be converted safely on the server. Export H.264/AAC MP4 and retry.') from None
                        from django.core.files import File
                        with open(output,'rb') as raw:
                            candidate=File(raw,name='converted.mp4')
                            validate_mp4(candidate)
                            client.put_object(Bucket=bucket,Key=converted,Body=candidate,ContentType='video/mp4')
                        storage._verify_upload(converted, os.path.getsize(output))
                    key=converted
                item = form.instance
                setattr(item, field, key)
                item.state = 'draft'
                item.save(actor=request.user)
                DICAdminAuditEvent.objects.create(actor=request.user, action='studio_media_draft_uploaded', target_type=model.__name__, target_id=str(item.pk), details={'library':kind,'direct':True})
                return self.nocache({'id':item.pk,'state':item.state},status=201)
        except ModelValidationError as error:
            raise ValidationError(error.messages) from error
        except (BotoCoreError, ClientError):
            raise TransferUnavailable() from None
