"""
Tests for the ingredients API.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import TestCase

from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Recipe,
    Ingredient,
)

from recipe.serializers import IngredientSerializer

INGREDIENTS_URL = reverse('recipe:ingredient-list')


def detail_url(ingredient_id):
    """
    Create and return a ingredient detail url.
    """
    return reverse('recipe:ingredient-detail', args=[ingredient_id])


def create_user(email='test@example.com', password='sampletest123'):
    """
    Create and return new user.
    """
    return get_user_model().objects.create(email=email, password=password)


def create_recipe(user, **params):
    """
    Create and return a sample recipe.
    """
    default = {
        'title': 'Sample recipe title',
        'time_minutes': 22,
        'price': Decimal('5.25'),
        'description': 'Sample recipe description',
        'link': 'https://example.com/recipe.pdf',
    }
    default.update(params)

    recipe = Recipe.objects.create(user=user, **default)
    return recipe


def create_ingredient(user, name='Ingredient'):
    """
    Create and return new ingredient
    """
    return Ingredient.objects.create(user=user, name=name)


class PublicIngredientApiTests(TestCase):
    """
    Test unauthenticated API requests.
    """

    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        """
        Test auth is required for retrieving ingredients.
        """
        res = self.client.get(INGREDIENTS_URL)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateIngredientApiTests(TestCase):
    """
    Test authenticated API requests.
    """

    def setUp(self):
        self.user = create_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_retrieve_ingredients(self):
        """
        Test retrieving a list of ingredients.
        """
        create_ingredient(user=self.user, name='Carrot')
        create_ingredient(user=self.user, name='Salmon')

        res = self.client.get(INGREDIENTS_URL)

        ingredients = Ingredient.objects.all().order_by('-name')
        serializer = IngredientSerializer(ingredients, many=True)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_ingredients_limited_to_user(self):
        """
        Test list of ingredients that is limited to authenticated user.
        """
        other_user = create_user(
            email='bob@example.com', password='samplebob123')

        create_ingredient(user=other_user, name='Sugar')
        ingredient = create_ingredient(user=self.user, name='Salt')

        res = self.client.get(INGREDIENTS_URL)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['id'], ingredient.id)
        self.assertEqual(res.data[0]['name'], ingredient.name)

    def test_update_ingredient(self):
        """
        Test updating an ingredient.
        """
        ingredient = create_ingredient(user=self.user, name='Onion')

        payload = {'name': 'Coriander'}
        res = self.client.patch(detail_url(ingredient.id), payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ingredient.refresh_from_db()
        self.assertEqual(ingredient.name, payload['name'])

    def test_delete_ingredient(self):
        """
        Test deleting an ingredient.
        """
        ingredient = create_ingredient(user=self.user, name='Broccoli')

        res = self.client.delete(detail_url(ingredient.id))

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        ingredients = Ingredient.objects.all() \
            .filter(user=self.user).order_by('-name')
        self.assertFalse(ingredients.exists())

    def test_filter_ingredients_assigned_to_recipes(self):
        """
        Test listing ingredients by those assigned to recipes.
        """
        ingredient1 = create_ingredient(user=self.user, name='Apple')
        ingredient2 = create_ingredient(user=self.user, name='Ground Beef')
        ingredient3 = create_ingredient(user=self.user, name='Cinnamon')

        recipe = create_recipe(user=self.user, title='Apple Pie')
        recipe.ingredients.add(ingredient1)
        recipe.ingredients.add(ingredient3)

        params = {
            'assigned_only': 1,
        }
        res = self.client.get(INGREDIENTS_URL, params)

        inSerializer1 = IngredientSerializer(ingredient1)
        inSerializer2 = IngredientSerializer(ingredient2)
        inSerializer3 = IngredientSerializer(ingredient3)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(inSerializer1.data, res.data)
        self.assertNotIn(inSerializer2.data, res.data)
        self.assertIn(inSerializer3.data, res.data)

    def test_filter_ingredients_unique(self):
        """
        Test filtered ingredients returns a unique list.
        """
        ingredient = create_ingredient(user=self.user, name='Egg')
        create_ingredient(user=self.user, name='Tomato')

        recipe1 = create_recipe(user=self.user, title='Egg Custard Pie')
        recipe2 = create_recipe(user=self.user, title='Omelette')
        recipe1.ingredients.add(ingredient)
        recipe2.ingredients.add(ingredient)

        params = {
            'assigned_only': 1,
        }
        res = self.client.get(INGREDIENTS_URL, params)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
