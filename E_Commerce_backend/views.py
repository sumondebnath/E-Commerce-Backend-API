from django.http import JsonResponse


def Health_Check(request):
    return JsonResponse({"status": "ok", "message": "E-Commerce Backend Service is running successfully."})