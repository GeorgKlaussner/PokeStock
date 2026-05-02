from django.urls import path

from collection import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("collection/", views.collection_list, name="collection_list"),
    path("cards/<str:external_id>/", views.card_detail, name="card_detail"),
    path("cards/<str:external_id>/refresh/", views.refresh_card, name="refresh_card"),
    path("add/", views.add_search, name="add_search"),
    path("add/sets/<str:set_id>/", views.add_set_cards, name="add_set_cards"),
    path("add/<str:external_id>/", views.add_owned_card, name="add_owned_card"),
    path("camera/", views.camera_add, name="camera_add"),
    path("camera/candidates/", views.camera_candidates, name="camera_candidates"),
    path("quick-add/<str:external_id>/", views.quick_add_card, name="quick_add_card"),
    path("sets/", views.sets_index, name="sets_index"),
    path("sets/refresh-catalog/", views.refresh_set_catalog_view, name="refresh_set_catalog"),
    path("sets/<str:set_id>/", views.set_detail, name="set_detail"),
    path("sets/<str:set_id>/refresh/", views.refresh_set, name="refresh_set"),
    path("refresh/", views.refresh_collection, name="refresh_collection"),
    path("csv/export/", views.export_csv, name="export_csv"),
    path("csv/import/", views.import_csv, name="import_csv"),
    path("ocr/", views.ocr_upload, name="ocr_upload"),
    path("ocr/<int:job_id>/", views.ocr_detail, name="ocr_detail"),
]
