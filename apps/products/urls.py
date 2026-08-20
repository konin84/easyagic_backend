from django.urls import path

from .views import (
    ProductCategoryListView,
    ProductDetailView,
    ProductListView,
    ProductsByCategoryView,
)

urlpatterns = [
    path("", ProductListView.as_view(), name="product-list"),
    path("categories/", ProductCategoryListView.as_view(), name="product-categories"),
    path("by-category/", ProductsByCategoryView.as_view(), name="products-by-category"),
    path("<slug:slug>/", ProductDetailView.as_view(), name="product-detail"),
]
