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
    # `str` not `slug`: the slug converter rejects spaces and punctuation, so
    # "Hand Hoe" or "Knapsack Sprayer (16 L)" never even reached the view.
    path("<str:identifier>/", ProductDetailView.as_view(), name="product-detail"),
]
