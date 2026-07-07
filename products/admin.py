from django.contrib import admin
from .models import Category, Product, Review, SaveProduct

# Register your models here.

class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    # search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}

admin.site.register(Category, CategoryAdmin)
admin.site.register(Product)    
admin.site.register(Review)
admin.site.register(SaveProduct)



