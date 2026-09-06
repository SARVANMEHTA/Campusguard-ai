from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q
from .models import SuspendedStudent, FaceEmbedding
from .forms import SuspendedStudentForm
from .embeddings import face_engine
from surveillance.matcher import matcher


def student_list(request):
    """View to list, search, and filter suspended students."""
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all')
    dept_filter = request.GET.get('dept', 'all')

    students = SuspendedStudent.objects.all().prefetch_related('embeddings')

    # Update expired status automatically
    for s in students:
        s.check_and_update_status()

    if query:
        students = students.filter(
            Q(student_id__icontains=query) |
            Q(full_name__icontains=query) |
            Q(department__icontains=query) |
            Q(suspension_reason__icontains=query)
        )

    if status_filter in ['active', 'expired']:
        students = students.filter(status=status_filter)

    departments = SuspendedStudent.objects.values_list('department', flat=True).distinct()

    context = {
        'students': students,
        'query': query,
        'status_filter': status_filter,
        'dept_filter': dept_filter,
        'departments': departments,
    }
    return render(request, 'dashboard/student_list.html', context)


def student_create(request):
    """View to register a new suspended student and extract face embeddings."""
    if request.method == 'POST':
        form = SuspendedStudentForm(request.POST, request.FILES)
        if form.is_valid():
            student = form.save(user=request.user if request.user.is_authenticated else None)
            
            # Handle additional photos if uploaded
            additional_files = request.FILES.getlist('additional_photos')
            extra_count = 0
            for extra_img in additional_files:
                try:
                    emb, crop_content = face_engine.process_image_file_for_embedding(extra_img)
                    FaceEmbedding.objects.create(
                        student=student,
                        embedding_vector=emb,
                        model_version="sface-128",
                        source_image=crop_content
                    )
                    extra_count += 1
                except Exception:
                    pass

            matcher.reload_cache()
            messages.success(
                request,
                f"Suspended student {student.full_name} ({student.student_id}) registered successfully with {student.embeddings.count()} reference face embedding(s)."
            )
            return redirect('students:student_detail', pk=student.pk)
        else:
            messages.error(request, "Please correct the errors below before submitting.")
    else:
        form = SuspendedStudentForm()

    return render(request, 'dashboard/student_form.html', {'form': form, 'title': 'Register Suspended Student'})


def student_detail(request, pk):
    """View student profile, enrolled embeddings, and historical detections."""
    student = get_object_or_404(SuspendedStudent, pk=pk)
    student.check_and_update_status()
    
    embeddings = student.embeddings.all()
    detections = student.detections.all().order_by('-timestamp')[:30]

    context = {
        'student': student,
        'embeddings': embeddings,
        'detections': detections,
    }
    return render(request, 'dashboard/student_detail.html', context)


def student_update(request, pk):
    """Edit student metadata or suspension period."""
    student = get_object_or_404(SuspendedStudent, pk=pk)
    
    if request.method == 'POST':
        form = SuspendedStudentForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            form.save(user=request.user if request.user.is_authenticated else None)
            matcher.reload_cache()
            messages.success(request, f"Details for {student.full_name} updated successfully.")
            return redirect('students:student_detail', pk=student.pk)
    else:
        form = SuspendedStudentForm(instance=student)

    return render(request, 'dashboard/student_form.html', {
        'form': form,
        'student': student,
        'title': f'Edit Student - {student.full_name}'
    })


def student_delete(request, pk):
    """Delete student record."""
    student = get_object_or_404(SuspendedStudent, pk=pk)
    if request.method == 'POST':
        name = student.full_name
        student.delete()
        matcher.reload_cache()
        messages.success(request, f"Suspended student record '{name}' deleted.")
        return redirect('students:student_list')
    return redirect('students:student_detail', pk=pk)


def student_toggle_status(request, pk):
    """Quick toggle between active and expired status."""
    student = get_object_or_404(SuspendedStudent, pk=pk)
    if student.status == 'active':
        student.status = 'expired'
    else:
        student.status = 'active'
    student.save(update_fields=['status'])
    matcher.reload_cache()
    messages.info(request, f"Status for {student.full_name} updated to {student.get_status_display()}.")
    return redirect('students:student_detail', pk=pk)


def add_embedding(request, pk):
    """Add extra angle/lighting embedding photo to an existing student."""
    student = get_object_or_404(SuspendedStudent, pk=pk)
    if request.method == 'POST' and 'photo' in request.FILES:
        photo = request.FILES['photo']
        try:
            emb, crop_content = face_engine.process_image_file_for_embedding(photo)
            FaceEmbedding.objects.create(
                student=student,
                embedding_vector=emb,
                model_version="sface-128",
                source_image=crop_content
            )
            matcher.reload_cache()
            messages.success(request, "New reference face angle added successfully.")
        except Exception as e:
            messages.error(request, f"Failed to extract face embedding: {str(e)}")
            
    return redirect('students:student_detail', pk=pk)
