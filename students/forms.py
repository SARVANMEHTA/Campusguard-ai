from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import SuspendedStudent, FaceEmbedding
from .embeddings import face_engine


class SuspendedStudentForm(forms.ModelForm):
    additional_photos = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*',
            'id': 'additionalPhotosInput'
        }),
        help_text="Optional: Upload extra photos from different angles/lighting to enhance recognition accuracy."
    )

    class Meta:
        model = SuspendedStudent
        fields = [
            'student_id',
            'full_name',
            'photo',
            'department',
            'year',
            'suspension_reason',
            'suspension_start_date',
            'suspension_end_date',
            'status'
        ]
        widgets = {
            'student_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 21BCE1045 / CS-2022-09'}),
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Rahul Sharma'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*', 'id': 'primaryPhotoInput'}),
            'department': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Computer Science & Engineering'}),
            'year': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 4th Year / 7th Sem'}),
            'suspension_reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Specific disciplinary reason, incident details, committee decision...'}),
            'suspension_start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'suspension_end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('suspension_start_date')
        end = cleaned_data.get('suspension_end_date')

        if start and end and end < start:
            raise ValidationError("Suspension end date cannot be earlier than start date.")

        return cleaned_data

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo:
            try:
                # Test face detection on uploaded photo
                embedding, crop_content = face_engine.process_image_file_for_embedding(photo)
                # Cache embedding on form instance for save()
                self._primary_embedding = embedding
                self._primary_crop = crop_content
            except Exception as e:
                raise ValidationError(f"Face verification failed: {str(e)}")
        return photo

    def save(self, commit=True, user=None):
        instance = super().save(commit=False)
        if user and not instance.added_by:
            instance.added_by = user
            
        if commit:
            instance.save()
            # Save extracted primary embedding
            if hasattr(self, '_primary_embedding') and self._primary_embedding:
                FaceEmbedding.objects.create(
                    student=instance,
                    embedding_vector=self._primary_embedding,
                    model_version="sface-128",
                    source_image=getattr(self, '_primary_crop', None)
                )
                
            # Reload surveillance matcher in-memory cache
            try:
                from surveillance.matcher import matcher
                matcher.reload_cache()
            except Exception:
                pass
                
        return instance
