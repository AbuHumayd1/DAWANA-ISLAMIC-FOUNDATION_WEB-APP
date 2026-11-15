"""Private bounded recording storage, using the existing media R2 boundary."""
import io
import json
import os
from pathlib import PurePosixPath, Path
import subprocess
import tempfile
import uuid
from django.core.exceptions import ValidationError
from django.core.files import File
from django.utils.deconstruct import deconstructible
from django.conf import settings
from .memory_storage import PrivateMemoryStorage

MAX_RECORDING=200*1024*1024


def safe_key(name):
    if not isinstance(name,str) or not name or chr(92) in name or chr(0) in name or ':' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
        raise ValidationError('Invalid private object key.')
    return name


def validate_recording(upload, video=False):
    if not 0 < upload.size <= MAX_RECORDING: raise ValidationError('Recordings must be nonempty and no larger than 200 MB.')
    suffix=Path(upload.name).suffix.lower()
    if suffix not in (['.mp4','.webm'] if video else ['.mp3','.m4a','.wav','.ogg']):
        raise ValidationError('Use an approved MP3, M4A, WAV or Ogg audio file, or MP4/WebM video.')
    name=None
    try:
        upload.seek(0)
        with tempfile.NamedTemporaryFile(suffix=suffix,delete=False) as temp:
            name=temp.name
            for chunk in upload.chunks(): temp.write(chunk)
        result=subprocess.run([getattr(settings,'DIC_FFPROBE_BINARY','ffprobe'),'-v','error','-show_entries','stream=codec_type,codec_name','-of','json',name],
            capture_output=True,timeout=20,check=True)
        streams=json.loads(result.stdout).get('streams',[])
        expected='video' if video else 'audio'
        if not any(s.get('codec_type')==expected for s in streams) or (not video and any(s.get('codec_type')=='video' for s in streams)):
            raise ValueError
    except (OSError,ValueError,subprocess.SubprocessError):
        raise ValidationError('The recording could not be validated. A working ffprobe installation and supported media are required.') from None
    finally:
        upload.seek(0)
        if name: os.unlink(name)


@deconstructible
class RecordingStorage(PrivateMemoryStorage):
    def _save(self,name,content):
        safe_key(name)
        suffix=Path(name).suffix.lower()
        validate_recording(content,video=suffix in ('.mp4','.webm'))
        key='camp-recordings/'+uuid.uuid4().hex+suffix
        backend=self._backend()
        if backend is not None: return backend.save(key,content)
        content.seek(0)
        mime={'.mp3':'audio/mpeg','.m4a':'audio/mp4','.wav':'audio/wav','.ogg':'audio/ogg','.mp4':'video/mp4','.webm':'video/webm'}[suffix]
        self._client().put_object(Bucket=self._bucket(),Key=key,Body=content,
            ContentType=mime,IfNoneMatch='*')
        self._verify_upload(key,content.size)
        return key
    def _open(self,name,mode='rb'):
        safe_key(name)
        backend=self._backend()
        if backend is not None: return backend.open(name,mode)
        result=self._client().get_object(Bucket=self._bucket(),Key=name)
        if result.get('ContentLength',MAX_RECORDING+1)>MAX_RECORDING:
            result['Body'].close();raise ValidationError('Stored recording exceeds the size limit.')
        temp=tempfile.SpooledTemporaryFile(max_size=8*1024*1024)
        count=0
        try:
            while True:
                chunk=result['Body'].read(1024*1024)
                if not chunk: break
                count+=len(chunk)
                if count>MAX_RECORDING: raise ValidationError('Stored recording exceeds the size limit.')
                temp.write(chunk)
            temp.seek(0)
            return File(temp,name=name)
        except Exception:
            temp.close();raise
        finally: result['Body'].close()


recording_storage=RecordingStorage()


def validate_video(upload): return validate_recording(upload,video=True)
