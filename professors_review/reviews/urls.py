from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'reviews'

urlpatterns = [
    path('', views.home, name='home'),
    path('professor/<int:pk>/', views.professor_detail, name='professor_detail'),
    path('vote-review/', views.vote_review, name='vote_review'),
    path('vote-answer/', views.vote_answer_ajax, name='vote_answer_ajax'),
    path('live-search/', views.live_search_professors, name='live_search'),
    path('daily-stats/', views.user_daily_stats, name='user_daily_stats'),
    
    # احراز هویت
    path('login/', views.custom_login, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name='logout'),
    path('signup/', views.signup, name='signup'),
    
    # جستجوی اساتید (صفحه جداگانه)
    path('search/', views.search_professors, name='search_professors'),
]