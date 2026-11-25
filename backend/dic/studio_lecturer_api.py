"""Media Studio authoring for DIC lecturer appearances.

Uses the same models, locks, verification, publisher grants and audit events as
Django Admin. No duplicate publication database or public endpoint.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from .models import CampEdition, DICAdminAuditEvent
from .showcase_models import Lecturer, LecturerAppearance
from .studio_api import StudioView, upload_enabled


def grant(user, action):
    return user.is_superuser or user.has_perm('dic.' + action + '_lecturerappearance')


def require_grant(user, action):
    if not grant(user, action):
        raise PermissionDenied('Lecturer appearance ' + action + ' permission required.')


def read_fields(data, creating=False):
    allowed = {'lecturer', 'edition', 'participation_type', 'topic', 'featured',
               'display_order', 'verification_note', 'confirmation_status'}
    if not isinstance(data, dict) or not data or not set(data) <= allowed:
        raise ValidationError({'detail': 'Only approved lecturer appearance fields are allowed.'})
    if creating and not {'lecturer', 'edition', 'participation_type'} <= set(data):
        raise ValidationError({'detail': 'Choose an existing lecturer, edition and appearance type.'})
    fields = {}
    for key, value in data.items():
        if key in ('lecturer', 'edition'):
            if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit() or not 0 < len(str(value)) <= 9:
                raise ValidationError({key: 'Choose an existing record.'})
            fields[key + '_id'] = int(value)
        elif key == 'participation_type':
            if value not in ('previous', 'upcoming'):
                raise ValidationError({key: 'Choose previous or upcoming.'})
            fields[key] = value
        elif key == 'confirmation_status':
            if value not in ('pending', 'invited', 'declined'):
                raise ValidationError({key: 'Use the separate Verify action for confirmed status.'})
            fields[key] = value
        elif key in ('topic', 'verification_note'):
            maximum = 300 if key == 'topic' else 5000
            if not isinstance(value, str) or len(value) > maximum:
                raise ValidationError({key: 'Invalid or oversized text.'})
            fields[key] = value.strip()
        elif key == 'featured':
            if not isinstance(value, bool):
                raise ValidationError({key: 'Choose true or false.'})
            fields[key] = value
        elif key == 'display_order':
            if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit() or int(value) > 999999:
                raise ValidationError({key: 'Choose a valid display order.'})
            fields[key] = int(value)
    return fields


def serialize(item):
    return {
        'id': item.pk, 'lecturer': item.lecturer_id, 'lecturer_name': item.lecturer.name, 'biography': item.lecturer.biography,
        'edition': item.edition_id, 'edition_name': item.edition.name,
        'participation_type': item.participation_type, 'topic': item.topic,
        'confirmation_status': item.confirmation_status,
        'verified': item.verified, 'verification_note': item.verification_note,
        'state': item.state, 'featured': item.featured,
        'display_order': item.display_order,
        'published_at': item.published_at,
        'image_url': reverse('dic:showcase-image', args=['lecturer', item.pk]) + '?preview=1',
    }


def audit(request, obj, action, fields=None):
    DICAdminAuditEvent.objects.create(
        actor=request.user, action=action,
        target_type='LecturerAppearance', target_id=str(obj.pk),
        details={'fields': sorted(fields or ())},
    )


def validate_and_save(item, actor):
    try:
        item.full_clean()
        item.save(actor=actor)
    except DjangoValidationError as error:
        raise ValidationError({'detail': error.message_dict if hasattr(error, 'message_dict') else error.messages}) from error


class StudioLecturerAppearancesView(StudioView):
    def get(self, request):
        require_grant(request.user, 'view')
        # Constrain user-supplied pagination; avoid unbounded catalogue responses.
        raw_page = request.query_params.get('page', '1')
        if not raw_page.isascii() or not raw_page.isdigit() or len(raw_page) > 3 or not 1 <= int(raw_page) <= 100:
            raise ValidationError({'page': 'Choose a page from 1 to 100.'})
        page = int(raw_page)
        records = list(LecturerAppearance.objects.select_related('lecturer', 'edition')
                       .order_by('-pk')[(page - 1) * 30:page * 30 + 1])
        # Profiles are read-only selectors here; only previously saved identities.
        profiles = list(Lecturer.objects.order_by('name', 'pk').values('id', 'name', 'designation')[:500])
        editions = list(CampEdition.objects.order_by('-year').values('id', 'name', 'year')[:100])
        return self.nocache({
            'items': [serialize(x) for x in records[:30]],
            'has_more': len(records) > 30, 'page': page,
            'lecturers': profiles, 'editions': editions,
            'can_create': grant(request.user, 'add') and grant(request.user, 'change') and grant(request.user, 'publish') and (request.user.is_superuser or request.user.has_perm('dic.add_lecturer')),
            'can_delete': grant(request.user, 'change') and grant(request.user, 'publish'),
            'can_edit': grant(request.user, 'change'),
            'can_verify': grant(request.user, 'change') and grant(request.user, 'verify'),
            'can_publish': grant(request.user, 'change') and grant(request.user, 'publish'),
        })

    def post(self, request):
        require_grant(request.user, 'add')
        fields = read_fields(request.data, creating=True)
        if 'confirmation_status' in fields and fields['confirmation_status'] == 'declined':
            raise ValidationError({'confirmation_status': 'Do not create a declined public appearance.'})
        with transaction.atomic():
            if not Lecturer.objects.filter(pk=fields['lecturer_id']).exists():
                raise ValidationError({'lecturer': 'Choose a saved lecturer profile.'})
            if not CampEdition.objects.filter(pk=fields['edition_id']).exists():
                raise ValidationError({'edition': 'Choose an existing camp edition.'})
            if LecturerAppearance.objects.filter(
                lecturer_id=fields['lecturer_id'], edition_id=fields['edition_id']).exists():
                raise ValidationError({'detail': 'This lecturer already has an appearance for that edition. Edit the existing record.'})
            item = LecturerAppearance(**fields, state='draft')
            try:
                validate_and_save(item, request.user)
            except IntegrityError:
                raise ValidationError({'detail': 'That lecturer and edition already have an appearance.'}) from None
            audit(request, item, 'showcase_created', fields)
        return self.nocache({'item': serialize(item)}, status=201)


class StudioLecturerAppearanceDetailView(StudioView):
    def _locked(self, pk):
        # Preserve Django Admin's documented lock ordering: lecturer first.
        lecturer_id = LecturerAppearance.objects.filter(pk=pk).values_list('lecturer_id', flat=True).first()
        if not lecturer_id:
            raise NotFound('Lecturer appearance not found.')
        Lecturer.objects.select_for_update().get(pk=lecturer_id)
        return LecturerAppearance.objects.select_for_update().select_related('lecturer', 'edition').get(pk=pk)

    def patch(self, request, pk):
        require_grant(request.user, 'change')
        fields = read_fields(request.data)
        # Editing a verified record may change the evidence; original save() resets
        # confirmation appropriately. Do not allow a verified actor to be forged.
        with transaction.atomic():
            item = self._locked(pk)
            if 'lecturer_id' in fields and fields['lecturer_id'] != item.lecturer_id:
                raise ValidationError({'lecturer': 'Create a new appearance rather than transferring an existing lecturer record.'})
            if 'edition_id' in fields and fields['edition_id'] != item.edition_id:
                raise ValidationError({'edition': 'Do not transfer a recorded appearance between editions.'})
            item.state = 'review' if item.state == 'published' else item.state
            for key, value in fields.items():
                setattr(item, key, value)
            validate_and_save(item, request.user)
            audit(request, item, 'showcase_edited', fields)
        return self.nocache({'item': serialize(item)})

    def post(self, request, pk):
        action = request.data.get('action') if isinstance(request.data, dict) else None
        if action not in ('verify', 'publish', 'withdraw'):
            raise ValidationError({'action': 'Choose verify, publish or withdraw.'})
        if action == 'verify':
            require_grant(request.user, 'change')
            require_grant(request.user, 'verify')
        else:
            require_grant(request.user, 'change')
            require_grant(request.user, 'publish')
        with transaction.atomic():
            item = self._locked(pk)
            if action == 'verify':
                if item.confirmation_status == 'declined':
                    raise ValidationError({'detail': 'A declined appearance cannot be verified.'})
                if not item.verification_note.strip():
                    raise ValidationError({'verification_note': 'Save evidence before verifying participation and topic.'})
                # A second verification must not create a misleading fresh claim.
                item.state = 'review'
                item.confirmation_status = 'confirmed'
                validate_and_save(item, request.user)
                audit(request, item, 'lecturer_participation_verified')
            else:
                item.state = 'published' if action == 'publish' else 'review'
                validate_and_save(item, request.user)
                audit(request, item, 'showcase_published' if action == 'publish' else 'showcase_withdrawn')
        return self.nocache({'item': serialize(item)})


class StudioSimpleLecturerView(StudioView):
    """One-step Media Studio lecturer publishing; existing showcase remains unchanged."""
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        for action in ('add', 'change', 'publish'):
            require_grant(request.user, action)
        if not (request.user.is_superuser or request.user.has_perm('dic.add_lecturer')):
            raise PermissionDenied('Ask an administrator to enable lecturer uploads for your account.')
        if not upload_enabled():
            raise ValidationError({'flyer': 'Image uploads are currently unavailable. Please contact the administrator.'})
        flyer = request.FILES.get('flyer')
        if not flyer:
            raise ValidationError({'flyer': 'Choose the lecturer flyer or photograph to upload.'})
        raw_edition = str(request.data.get('edition', ''))
        if not raw_edition.isascii() or not raw_edition.isdigit() or len(raw_edition) > 9:
            raise ValidationError({'edition': 'Choose the camp year.'})
        edition = CampEdition.objects.filter(pk=int(raw_edition)).first()
        if edition is None:
            raise ValidationError({'edition': 'Choose an available camp year.'})
        appearance_type = request.data.get('participation_type', 'previous')
        if appearance_type not in ('previous', 'upcoming'):
            raise ValidationError({'participation_type': 'Choose previous or upcoming lecturer.'})
        name = str(request.data.get('name', '')).strip() or 'Lecturer'
        biography = str(request.data.get('biography', '')).strip()
        if len(name) > 200 or len(biography) > 2000:
            raise ValidationError({'detail': 'Please shorten the optional lecturer details.'})
        with transaction.atomic():
            lecturer = Lecturer(name=name, biography=biography, designation='',
                                alt_text='Flyer or portrait of ' + name, photograph=flyer)
            try:
                lecturer.full_clean(exclude=['biography'])
                lecturer.save()
            except DjangoValidationError as error:
                raise ValidationError({'flyer': 'Please select a valid JPEG, PNG or WebP image.'}) from error
            appearance = LecturerAppearance(lecturer=lecturer, edition=edition,
                participation_type=appearance_type, state='published')
            validate_and_save(appearance, request.user)
            audit(request, appearance, 'studio_lecturer_created_published', ('flyer', 'name', 'biography', 'edition'))
        return self.nocache({'item': serialize(appearance)}, status=201)


class StudioSimpleLecturerDetailView(StudioView):
    """Edit-and-publish or delete a lecturer through one staff action."""
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def patch(self, request, pk):
        require_grant(request.user, 'change')
        require_grant(request.user, 'publish')
        with transaction.atomic():
            lecturer_id = LecturerAppearance.objects.filter(pk=pk).values_list('lecturer_id', flat=True).first()
            if lecturer_id is None:
                raise NotFound('This lecturer no longer exists.')
            lecturer = Lecturer.objects.select_for_update().get(pk=lecturer_id)
            appearance = LecturerAppearance.objects.select_for_update().get(pk=pk)
            fields = []
            for key in ('name', 'biography'):
                if key in request.data:
                    value = str(request.data[key]).strip()
                    if len(value) > (200 if key == 'name' else 2000):
                        raise ValidationError({key: 'Please shorten this text.'})
                    if key == 'name' and not value:
                        raise ValidationError({key: 'Enter a lecturer name or leave the existing name unchanged.'})
                    setattr(lecturer, key, value)
                    fields.append(key)
            flyer = request.FILES.get('flyer')
            if flyer:
                lecturer.photograph = flyer
                fields.append('flyer')
            if fields:
                lecturer.alt_text = 'Flyer or portrait of ' + lecturer.name
                try:
                    lecturer.full_clean(exclude=['biography'])
                    lecturer.save()
                except DjangoValidationError as error:
                    raise ValidationError({'flyer': 'Please select a valid JPEG, PNG or WebP image.'}) from error
            if fields or appearance.confirmation_status == 'declined':
                # Identity edits invalidate the previous participation verification;
                # routine publication must never silently re-verify historical claims.
                appearance.confirmation_status = 'pending'
            appearance.state = 'published'
            validate_and_save(appearance, request.user)
            audit(request, appearance, 'studio_lecturer_updated_published', fields)
        return self.nocache({'item': serialize(appearance)})

    def delete(self, request, pk):
        require_grant(request.user, 'change')
        require_grant(request.user, 'publish')
        with transaction.atomic():
            lecturer_id = LecturerAppearance.objects.filter(pk=pk).values_list('lecturer_id', flat=True).first()
            if lecturer_id is None:
                raise NotFound('This lecturer has already been deleted.')
            lecturer = Lecturer.objects.select_for_update().get(pk=lecturer_id)
            appearance = LecturerAppearance.objects.select_for_update().get(pk=pk)
            audit(request, appearance, 'studio_lecturer_deleted', ('lecturer',))
            appearance.delete()
            # Retain identity and private file whenever another record references
            # them or the user lacks explicit identity-deletion permission.
            if not LecturerAppearance.objects.filter(lecturer_id=lecturer.pk).exists() and (
                    request.user.is_superuser or request.user.has_perm('dic.delete_lecturer')):
                try:
                    lecturer.delete()
                except ProtectedError:
                    pass
        return self.nocache({'deleted': True, 'id': pk})
