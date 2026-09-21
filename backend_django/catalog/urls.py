from django.urls import path

from . import views

urlpatterns = [
    path("godowns", views.get_godowns),
    path("meta", views.get_meta),

    path("auth/login", views.login),

    path("slabs", views.slabs_collection),
    path("slabs/<str:slab_id>", views.slab_detail),

    path("trash", views.list_trash),
    path("trash/<str:trash_id>/restore", views.restore_trash),
    path("trash/<str:trash_id>", views.purge_trash_item),

    path("queries", views.queries_collection),
    path("queries/<str:query_id>", views.update_query),

    path("announcements", views.announcements_collection),  # GET: active only (public) / POST: create (staff)
    path("announcements/all", views.list_all_announcements),
    path("announcements/<str:ann_id>", views.announcement_detail),

    path("reports/summary", views.reports_summary),
    path("reports/export.csv", views.export_csv),

    path("calc/area", views.calc_area),

    path("health", views.health),
]
