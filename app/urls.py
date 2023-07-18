from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("upload", views.upload_image, name="upload_image"),
    path("extract", views.extract_process, name="extract_process"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)