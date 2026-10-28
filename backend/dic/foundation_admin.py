from django.contrib import admin
from .models import ContactEnquiry, FoundationDonation, DICAdminAuditEvent


@admin.register(ContactEnquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display=('id','subject','status','created_at')
    list_filter=('status','created_at')
    search_fields=('subject','name','email')
    readonly_fields=('id','name','email','subject','message','created_at','updated_at')
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
    def save_model(self,request,obj,form,change):
        super().save_model(request,obj,form,change)
        DICAdminAuditEvent.objects.create(actor=request.user,action='foundation_enquiry_status',target_type='ContactEnquiry',target_id=str(obj.pk),details={'status':obj.status})


@admin.register(FoundationDonation)
class DonationAdmin(admin.ModelAdmin):
    list_display=('reference','amount_kobo','currency','status','created_at')
    list_filter=('status','created_at')
    search_fields=('reference',)
    fields=('reference','amount_kobo','currency','status','audit','created_at','updated_at')
    readonly_fields=fields
    def has_module_permission(self,request): return self.has_view_permission(request)
    def has_view_permission(self,request,obj=None): return request.user.is_active and request.user.is_staff and request.user.has_perm('dic.view_foundation_donations')
    def has_add_permission(self,request): return False
    def has_change_permission(self,request,obj=None): return False
    def has_delete_permission(self,request,obj=None): return False
