from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.contrib import messages
from django.utils import timezone
import datetime

from .models import Professor, Review, Question, Answer, AnswerVote, ReviewVote, UserDailyLimit
from .forms import ReviewForm, QuestionForm, AnswerForm, SignUpForm, ProfessorSearchForm, LoginForm

# =========================
# ثابت‌های سیستم
# =========================
DAILY_REVIEW_LIMIT = 3  # تغییر از ۴ به ۳
DAILY_QUESTION_LIMIT = 3  # تغییر از ۴ به ۳

# =========================
# Helper Functions
# =========================
def check_daily_limit(user, limit_type):
    """بررسی محدودیت روزانه کاربر"""
    try:
        daily_limit = UserDailyLimit.get_or_create_today(user)
        
        if limit_type == 'review':
            if not daily_limit.can_post_review:
                return False, f"شما امروز {DAILY_REVIEW_LIMIT} نظر ارسال کرده‌اید. فردا مجدد تلاش کنید."
            return True, "مجاز"
        
        elif limit_type == 'question':
            if not daily_limit.can_post_question:
                return False, f"شما امروز {DAILY_QUESTION_LIMIT} پرسش ارسال کرده‌اید. فردا مجدد تلاش کنید."
            return True, "مجاز"
        
    except Exception as e:
        return True, "خطا در بررسی محدودیت"


# =========================
# Home + Search
# =========================
def home(request):
    query = request.GET.get('query', '').strip()
    professors = Professor.objects.all()
    if query:
        professors = professors.filter(
            Q(name__icontains=query) | Q(department__icontains=query)
        )
    return render(request, 'reviews/home.html', {
        'professors': professors,
        'query': query
    })


# =========================
# Signup
# =========================
def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'ثبت‌نام با موفقیت انجام شد!')
            return redirect('reviews:home')
        else:
            messages.error(request, 'لطفاً خطاهای زیر را اصلاح کنید.')
    else:
        form = SignUpForm()
    
    # پاس دادن سوال ریاضی به تمپلیت
    challenge_question = form.get_challenge_question() if hasattr(form, 'get_challenge_question') else ''
    
    return render(request, 'reviews/signup.html', {
        'form': form,
        'challenge_question': challenge_question
    })


# =========================
# Login
# =========================
def custom_login(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, 'ورود موفقیت‌آمیز بود!')
                return redirect('reviews:home')
        else:
            # اگر فرم invalid بود، دوباره سوال جدید ایجاد نکن
            # فرم با خطاهایش بازگردانده می‌شود
            pass
    else:
        form = LoginForm()
    
    # پاس دادن سوال ریاضی به تمپلیت
    challenge_question = form.get_challenge_question() if hasattr(form, 'get_challenge_question') else ''
    
    return render(request, 'reviews/login.html', {
        'form': form,
        'challenge_question': challenge_question
    })


# =========================
# Search Professors
# =========================
def search_professors(request):
    form = ProfessorSearchForm(request.GET or None)
    results = None
    
    if form.is_valid():
        query = form.cleaned_data['query']
        if query:
            results = Professor.objects.filter(
                Q(name__icontains=query) | Q(department__icontains=query)
            )
    
    return render(request, 'reviews/search.html', {
        'form': form,
        'results': results
    })


# =========================
# Professor Detail
# =========================
@login_required
def professor_detail(request, pk):
    professor = get_object_or_404(Professor, pk=pk)

    reviews = Review.objects.filter(
        professor=professor,
        is_approved=True
    ).order_by('-created_at')

    questions = Question.objects.filter(
        professor=professor,
        is_approved=True
    ).order_by('-created_at')

    for question in questions:
        question.answers_approved = question.answers.filter(is_approved=True)

    review_form = ReviewForm()
    question_form = QuestionForm()
    answer_form = AnswerForm()
    message = None
    error_message = None

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        # -------- Review --------
        if form_type == 'review':
            can_post, limit_message = check_daily_limit(request.user, 'review')
            
            if not can_post:
                messages.error(request, limit_message)
                return redirect('reviews:professor_detail', pk=pk)
            else:
                review_form = ReviewForm(request.POST)
                if review_form.is_valid():
                    # بررسی تکراری نبودن نظر (برای جلوگیری از double submit)
                    existing_review = Review.objects.filter(
                        user=request.user,
                        professor=professor,
                        text=review_form.cleaned_data['text'],
                        rating=review_form.cleaned_data['rating'],
                        created_at__date=datetime.date.today()
                    ).first()
                    
                    if existing_review:
                        messages.warning(request, 'این نظر قبلاً ثبت شده است.')
                        return redirect('reviews:professor_detail', pk=pk)
                    
                    review = review_form.save(commit=False)
                    review.professor = professor
                    review.user = request.user
                    review.is_approved = False
                    review.save()
                    
                    daily_limit = UserDailyLimit.get_or_create_today(request.user)
                    daily_limit.increment_review()
                    
                    messages.success(request, 'نظر شما ثبت شد و پس از تأیید نمایش داده می‌شود.')
                    
                    # مهم: PRG Pattern - بعد از POST باید redirect کنیم
                    return redirect('reviews:professor_detail', pk=pk)
                else:
                    error_message = 'لطفاً خطاهای فرم را اصلاح کنید.'

        # -------- Question --------
        elif form_type == 'question':
            can_post, limit_message = check_daily_limit(request.user, 'question')
            
            if not can_post:
                messages.error(request, limit_message)
                return redirect('reviews:professor_detail', pk=pk)
            else:
                question_form = QuestionForm(request.POST)
                if question_form.is_valid():
                    # بررسی تکراری نبودن پرسش (برای جلوگیری از double submit)
                    existing_question = Question.objects.filter(
                        user=request.user,
                        professor=professor,
                        text=question_form.cleaned_data['text'],
                        created_at__date=datetime.date.today()
                    ).first()
                    
                    if existing_question:
                        messages.warning(request, 'این پرسش قبلاً ثبت شده است.')
                        return redirect('reviews:professor_detail', pk=pk)
                    
                    question = question_form.save(commit=False)
                    question.professor = professor
                    question.user = request.user
                    question.is_approved = False
                    question.save()
                    
                    daily_limit = UserDailyLimit.get_or_create_today(request.user)
                    daily_limit.increment_question()
                    
                    messages.success(request, 'پرسش شما ثبت شد و پس از تأیید نمایش داده می‌شود.')
                    
                    # مهم: PRG Pattern - بعد از POST باید redirect کنیم
                    return redirect('reviews:professor_detail', pk=pk)
                else:
                    error_message = 'لطفاً خطاهای فرم را اصلاح کنید.'

        # -------- Answer --------
        elif form_type == 'answer':
            question = get_object_or_404(
                Question,
                id=request.POST.get('question_id'),
                professor=professor,
                is_approved=True
            )
            answer_form = AnswerForm(request.POST)
            if answer_form.is_valid():
                # بررسی تکراری نبودن پاسخ (برای جلوگیری از double submit)
                existing_answer = Answer.objects.filter(
                    user=request.user,
                    question=question,
                    text=answer_form.cleaned_data['text'],
                    created_at__date=datetime.date.today()
                ).first()
                
                if existing_answer:
                    messages.warning(request, 'این پاسخ قبلاً ثبت شده است.')
                    return redirect('reviews:professor_detail', pk=pk)
                
                answer = answer_form.save(commit=False)
                answer.question = question
                answer.user = request.user
                answer.is_approved = False
                answer.save()
                messages.success(request, 'پاسخ شما ثبت شد و پس از تأیید نمایش داده می‌شود.')
                
                # مهم: PRG Pattern - بعد از POST باید redirect کنیم
                return redirect('reviews:professor_detail', pk=pk)
            else:
                error_message = 'لطفاً خطاهای فرم را اصلاح کنید.'

    # بعد از redirect، پیام‌ها را از session بخوان
    storage = messages.get_messages(request)
    for message in storage:
        if message.tags == 'success':
            message = str(message)
        elif message.tags == 'error':
            error_message = str(message)

    daily_limit = UserDailyLimit.get_or_create_today(request.user)
    review_limit_info = {
        'remaining': DAILY_REVIEW_LIMIT - daily_limit.review_count,
        'total': DAILY_REVIEW_LIMIT,
        'reached_limit': daily_limit.review_count >= DAILY_REVIEW_LIMIT
    }
    
    question_limit_info = {
        'remaining': DAILY_QUESTION_LIMIT - daily_limit.question_count,
        'total': DAILY_QUESTION_LIMIT,
        'reached_limit': daily_limit.question_count >= DAILY_QUESTION_LIMIT
    }

    context = {
        'professor': professor,
        'reviews': reviews,
        'questions': questions,
        'review_form': review_form,
        'question_form': question_form,
        'answer_form': answer_form,
        'message': message,
        'error_message': error_message,
        'review_limit': review_limit_info,
        'question_limit': question_limit_info,
        'DAILY_REVIEW_LIMIT': DAILY_REVIEW_LIMIT,  # برای استفاده در تمپلیت
        'DAILY_QUESTION_LIMIT': DAILY_QUESTION_LIMIT,  # برای استفاده در تمپلیت
    }
    return render(request, 'reviews/professor_detail.html', context)


# =========================
# Vote Review (AJAX)
# =========================
@login_required
def vote_review(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=400)

    review_id = request.POST.get("review_id")
    value = request.POST.get("value")
    
    if not review_id or not value:
        return JsonResponse({"error": "Missing parameters"}, status=400)
    
    try:
        value = int(value)
        if value not in (1, -1):
            return JsonResponse({"error": "Invalid value"}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Value must be integer"}, status=400)

    try:
        review = Review.objects.get(id=review_id, is_approved=True)
    except Review.DoesNotExist:
        return JsonResponse({"error": "Review not found or not approved"}, status=404)

    vote, created = ReviewVote.objects.get_or_create(
        review=review,
        user=request.user,
        defaults={"value": value}
    )

    if not created and vote.value == value:
        vote.delete()
    else:
        vote.value = value
        vote.save()

    likes_count = review.likes_count()
    dislikes_count = review.dislikes_count()

    return JsonResponse({
        "likes_count": likes_count,
        "dislikes_count": dislikes_count
    })


# =========================
# Vote Answer (AJAX)
# =========================
@login_required
def vote_answer_ajax(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=400)

    answer_id = request.POST.get("answer_id")
    value = request.POST.get("value")
    
    if not answer_id or not value:
        return JsonResponse({"error": "Missing parameters"}, status=400)
    
    try:
        value = int(value)
        if value not in (1, -1):
            return JsonResponse({"error": "Invalid value"}, status=400)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Value must be integer"}, status=400)

    try:
        answer = Answer.objects.get(id=answer_id, is_approved=True)
    except Answer.DoesNotExist:
        return JsonResponse({"error": "Answer not found or not approved"}, status=404)

    vote, created = AnswerVote.objects.get_or_create(
        answer=answer,
        user=request.user,
        defaults={"value": value}
    )

    if not created and vote.value == value:
        vote.delete()
    else:
        vote.value = value
        vote.save()

    likes_count = answer.likes_count()
    dislikes_count = answer.dislikes_count()

    return JsonResponse({
        "likes_count": likes_count,
        "dislikes_count": dislikes_count
    })


# =========================
# Live Search
# =========================
def live_search_professors(request):
    query = request.GET.get('query', '').strip()
    professors = Professor.objects.all()
    if query:
        professors = professors.filter(
            Q(name__icontains=query) | Q(department__icontains=query)
        )

    html = render_to_string(
        'reviews/partials/professor_list.html',
        {'professors': professors},
        request=request
    )
    return JsonResponse({'html': html})


# =========================
# User Daily Stats
# =========================
@login_required
def user_daily_stats(request):
    """نمایش آمار روزانه کاربر"""
    daily_limit = UserDailyLimit.get_or_create_today(request.user)
    
    return JsonResponse({
        'review_count': daily_limit.review_count,
        'question_count': daily_limit.question_count,
        'review_remaining': DAILY_REVIEW_LIMIT - daily_limit.review_count,
        'question_remaining': DAILY_QUESTION_LIMIT - daily_limit.question_count,
        'date': daily_limit.date.isoformat()
    })