from django.urls import path

from .views import ProductCategoryListView, ProductDetailView, ProductListView

urlpatterns = [
    path("", ProductListView.as_view(), name="product-list"),
    path("categories/", ProductCategoryListView.as_view(), name="product-categories"),
    path("<slug:slug>/", ProductDetailView.as_view(), name="product-detail"),
]
