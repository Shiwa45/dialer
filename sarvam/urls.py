# sarvam/urls.py
from django.urls import path
from . import views

app_name = 'sarvam'

urlpatterns = [
    path('tts/',                    views.generate_tts,     name='generate_tts'),
    path('tts/library/',            views.tts_library,      name='tts_library'),
    path('tts/play/<str:filename>/', views.tts_play,         name='tts_play'),
    path('tts/delete/',             views.tts_delete,        name='tts_delete'),
    path('tts/assign/',             views.tts_assign,        name='tts_assign'),
    path('tts/generate-ajax/',      views.tts_generate_ajax, name='tts_generate_ajax'),
]
