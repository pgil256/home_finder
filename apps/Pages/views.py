from django.shortcuts import render

def home(request):
    return render(request, 'Pages/home.html')

def about(request):
    return render(request, 'Pages/about.html')

def help(request):
    return render(request, 'Pages/help.html')


