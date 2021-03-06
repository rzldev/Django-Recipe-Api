"""
Tests for recipe APIs.
"""
from decimal import Decimal
import tempfile
import os

from PIL import Image

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Recipe,
    Tag,
    Ingredient,
)

from recipe.serializers import (
    RecipeSerializer,
    RecipeDetailSerializer,
)

RECIPES_URL = reverse('recipe:recipe-list')


def detail_url(recipe_id):
    """
    Create and return a recipe detail URL.
    """
    return reverse('recipe:recipe-detail', args=[recipe_id])


def image_upload_url(recipe_id):
    """
    Create and return an image upload URL.
    """
    return reverse('recipe:recipe-upload-image', args=[recipe_id])


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
    ingredient = Ingredient.objects.create(user=user, name=name)
    return ingredient


def create_user(**params):
    """
    Create and return a new user.
    """
    return get_user_model().objects.create_user(**params)


class PublicRecipeApiTests(TestCase):
    """
    Test unauthenticated API requests.
    """

    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        """
        Test auth is required to call API.
        """
        res = self.client.get(RECIPES_URL)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateRecipeApiTests(TestCase):
    """
    Test authenticated API requests.
    """

    def setUp(self):
        self.client = APIClient()
        self.user = create_user(email='test@example.com',
                                password='sampletest123')
        self.client.force_authenticate(self.user)

    def test_retrieve_recipe(self):
        """
        Test retrieving a list of recipes.
        """
        create_recipe(user=self.user)
        create_recipe(user=self.user)

        res = self.client.get(RECIPES_URL)

        recipes = Recipe.objects.all().order_by('-id')
        serializer = RecipeSerializer(recipes, many=True)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_recipe_list_limited_to_user(self):
        """
        Test list of recipe is limited to authenticated user.
        """
        other_user = create_user(
            email='bob@example.com', password='testbob123')
        create_recipe(other_user)
        create_recipe(self.user)

        res = self.client.get(RECIPES_URL)

        recipes = Recipe.objects.filter(user=self.user)
        serializer = RecipeSerializer(recipes, many=True)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_get_recipe_detail(self):
        """
        Test get recipe detail.
        """
        recipe = create_recipe(user=self.user)

        url = detail_url(recipe.id)
        res = self.client.get(url)

        serializer = RecipeDetailSerializer(recipe)
        self.assertEqual(res.data, serializer.data)

    def test_create_recipe(self):
        """
        Test creating a recipe.
        """
        payload = {
            'title': 'Sample recipe',
            'time_minutes': 30,
            'price': Decimal('5.99'),
        }
        res = self.client.post(RECIPES_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        recipe = Recipe.objects.get(id=res.data['id'])
        for k, v in payload.items():
            self.assertEqual(getattr(recipe, k), v)
        self.assertEqual(recipe.user, self.user)

    def test_partial_update(self):
        """
        Test partial update of a recipe.
        """
        original_link = 'https://example.com/recipe.pdf'
        recipe = create_recipe(
            user=self.user,
            title='Sample recipe title',
            link=original_link,
        )

        payload = {'title': 'New recipe title'}
        res = self.client.patch(detail_url(recipe.id), payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        self.assertEqual(recipe.title, payload['title'])
        self.assertEqual(recipe.link, original_link)
        self.assertEqual(recipe.user, self.user)

    def test_full_update(self):
        """
        Test full update of recipe.
        """
        recipe = create_recipe(
            user=self.user,
            title='Sample recipe title',
            link='https://example.com/recipe.pdf',
            time_minutes=30,
            description='This is a sample recipe description.',
        )

        payload = {
            'title': 'New recipe title',
            'link': 'https://example.com/new-recipe.pdf',
            'description': 'Successful updated recipe.',
            'time_minutes': 35,
            'price': Decimal('2.99')
        }

        res = self.client.put(detail_url(recipe.id), payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        for k, v in payload.items():
            self.assertEqual(getattr(recipe, k), v)
        self.assertEqual(recipe.user, self.user)

    def test_update_user_return_error(self):
        """
        Test changing the recipe user results in an error.
        """
        new_user = create_user(email='bob@example.com', password='bobtest123')
        recipe = create_recipe(user=self.user)

        payload = {'user': new_user.id}
        res = self.client.patch(detail_url(recipe.id), payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        self.assertEqual(recipe.user, self.user)

    def test_delete_recipe_successful(self):
        """
        Test deleting a recipe successful.
        """
        recipe = create_recipe(user=self.user)

        res = self.client.delete(detail_url(recipe.id))
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Recipe.objects.filter(id=recipe.id).exists())

    def test_delete_other_user_recipe_error(self):
        """
        Test trying to delete another users recipe gives an error.
        """
        other_user = create_user(
            email='bob@example.com', password='bobtest123')
        recipe = create_recipe(user=other_user)

        res = self.client.delete(detail_url(recipe.id))

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Recipe.objects.filter(id=recipe.id).exists())

    def test_create_recipe_with_new_tags(self):
        """
        Test creating a recipe with a new tags.
        """
        payload = {
            'title': 'Thai Prawn Curry',
            'time_minutes': 30,
            'price': Decimal('2.50'),
            'tags': [{'name': 'Thai'}, {'name': 'Dinner'}],
        }

        res = self.client.post(RECIPES_URL, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        recipes = Recipe.objects.filter(user=self.user)
        self.assertEqual(recipes.count(), 1)

        recipe = recipes[0]
        self.assertTrue(recipe.tags.count(), 2)

        for tag in payload['tags']:
            exists = recipe.tags.filter(
                name=tag['name'],
                user=self.user,
            ).exists()
            self.assertTrue(exists)

    def test_create_recipe_with_existing_tags(self):
        """
        Test creating a recipe with existing tags.
        """
        tag_chinese = Tag.objects.create(user=self.user, name='Indonesian')
        payload = {
            'title': 'Rendang',
            'time_minutes': 45,
            'price': Decimal('3.99'),
            'tags': [{'name': 'Indonesian'}, {'name': 'Rice'}],
        }
        res = self.client.post(RECIPES_URL, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        recipes = Recipe.objects.filter(user=self.user)
        self.assertTrue(recipes.count(), 1)

        recipe = recipes[0]
        self.assertTrue(recipe.tags.count(), 2)
        self.assertIn(tag_chinese, recipe.tags.all())

        for tag in payload['tags']:
            exists = recipe.tags.filter(
                name=tag['name'],
                user=self.user,
            ).exists()
            self.assertTrue(exists)

    def test_create_tag_on_update(self):
        """
        Test creating tag when updating a recipe.
        """
        recipe = create_recipe(user=self.user)

        payload = {'tags': [{'name': 'Lunch'}]}
        res = self.client.patch(detail_url(recipe.id), payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        new_tag = Tag.objects.get(user=self.user, name='Lunch')
        self.assertIn(new_tag, recipe.tags.all())

    def test_update_recipe_assign_tag(self):
        """
        Test assigning an existing tag when updating a recipe.
        """
        tag_breakfast = Tag.objects.create(user=self.user, name='Breakfast')
        recipe = create_recipe(user=self.user)
        recipe.tags.add(tag_breakfast)

        tag_lunch = Tag.objects.create(user=self.user, name='Lunch')
        payload = {'tags': [{'name': 'Lunch'}]}
        res = self.client.patch(detail_url(recipe.id), payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(tag_lunch, recipe.tags.all())
        self.assertNotIn(tag_breakfast, recipe.tags.all())

    def test_clear_recipe_tags(self):
        """
        Test clearing a recipe tags.
        """
        tag = Tag.objects.create(user=self.user, name='Beverage')
        recipe = create_recipe(user=self.user)
        recipe.tags.add(tag)

        payload = {'tags': []}
        res = self.client.patch(detail_url(recipe.id), payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(recipe.tags.count(), 0)

    def test_create_recipe_with_new_ingredients(self):
        """
        Test creating a recipe with new ingredients.
        """
        payload = {
            'title': 'Miso Soup',
            'time_minutes': 40,
            'price': Decimal('1.99'),
            'description': 'This is miso soup recipe.',
            'ingredients': [
                {'name': 'Dashi granules'},
                {'name': 'Miso paste'},
                {'name': 'Onion'},
            ],
        }

        res = self.client.post(RECIPES_URL, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        recipes = Recipe.objects.filter(user=self.user).order_by('-id')
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.ingredients.count(), 3)

        for ingredient in payload['ingredients']:
            exists = recipe.ingredients.filter(
                name=ingredient['name'],
                user=self.user,
            ).exists()
            self.assertTrue(exists)

    def test_create_recipe_with_exist_ingredients(self):
        """
        Testing creating a recipe with existed ingredients.
        """
        ingredient = create_ingredient(user=self.user, name='Lemon')

        payload = {
            'title': 'Lemonade',
            'time_minutes': 10,
            'price': Decimal('10'),
            'description': 'This is lemonade recipe',
            'ingredients': [
                {'name': 'Lemon'},
                {'name': 'Sugar'},
                {'name': 'Water'}
            ],
        }

        res = self.client.post(RECIPES_URL, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        recipes = Recipe.objects.filter(user=self.user).order_by('-id')
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.ingredients.count(), 3)
        self.assertIn(ingredient, recipe.ingredients.all())

        for ingredient in payload['ingredients']:
            exists = recipe.ingredients.filter(
                name=ingredient['name'],
                user=self.user,
            ).exists()
            self.assertTrue(exists)

    def test_create_ingredient_on_update(self):
        """
        Test creating an ingredient when updating recipe.
        """
        recipe = create_recipe(user=self.user)

        payload = {
            'ingredients': [{'name': 'Onion'}],
        }
        res = self.client.patch(detail_url(recipe.id), payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ingredient = Ingredient.objects.get(
            user=self.user, name=payload['ingredients'][0]['name'])
        self.assertIn(ingredient, recipe.ingredients.all())

    def test_update_recipe_assign_ingredient(self):
        """
        Test assigning an existing ingredient when updating a recipe.
        """
        ingredient1 = create_ingredient(user=self.user, name='Pepper')
        recipe = create_recipe(user=self.user)
        recipe.ingredients.add(ingredient1)

        ingredient2 = create_ingredient(user=self.user, name='Chili')
        payload = {
            'ingredients': [{'name': 'Chili'}]
        }
        res = self.client.patch(detail_url(recipe.id), payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(ingredient2, recipe.ingredients.all())
        self.assertNotIn(ingredient1, recipe.ingredients.all())

    def test_clear_ingredients(self):
        """
        Test clearing a recipes ingredients.
        """
        ingredient = create_ingredient(user=self.user, name='garlic')
        recipe = create_recipe(user=self.user)
        recipe.ingredients.add(ingredient)

        payload = {'ingredients': []}
        res = self.client.patch(detail_url(recipe.id), payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        self.assertEqual(recipe.ingredients.count(), 0)

    def test_filter_by_tags(self):
        """
        Test filtering recipes by tags.
        """
        recipe1 = create_recipe(user=self.user, title='Miso Soup')
        recipe2 = create_recipe(user=self.user, title='Wonton Soup')
        recipe3 = create_recipe(user=self.user, title='Tortelli')
        tag1 = Tag.objects.create(user=self.user, name='Soup')
        tag2 = Tag.objects.create(user=self.user, name='Chinese')
        recipe1.tags.add(tag1)
        recipe2.tags.add(tag1)
        recipe2.tags.add(tag2)

        params = {'tags': f'{tag1.id},{tag2.id}'}
        res = self.client.get(RECIPES_URL, params)

        recipeSerializer1 = RecipeSerializer(recipe1)
        recipeSerializer2 = RecipeSerializer(recipe2)
        recipeSerializer3 = RecipeSerializer(recipe3)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(recipeSerializer1.data, res.data)
        self.assertIn(recipeSerializer2.data, res.data)
        self.assertNotIn(recipeSerializer3.data, res.data)

    def test_filter_by_ingredients(self):
        """
        Test filtering recipes by ingredients.
        """
        recipe1 = create_recipe(user=self.user, title='Miso Soup')
        recipe2 = create_recipe(user=self.user, title='Wonton Soup')
        recipe3 = create_recipe(user=self.user, title='Tortelli')
        ingredient1 = create_ingredient(user=self.user, name='Pumpkin')
        ingredient2 = create_ingredient(user=self.user, name='Dashi')
        ingredient3 = create_ingredient(user=self.user, name='Ginger')
        recipe1.ingredients.add(ingredient1)
        recipe1.ingredients.add(ingredient2)
        recipe2.ingredients.add(ingredient3)
        recipe3.ingredients.add(ingredient1)

        params = {'ingredients': f'{ingredient1.id}'}
        res = self.client.get(RECIPES_URL, params)

        recipeSerializer1 = RecipeSerializer(recipe1)
        recipeSerializer2 = RecipeSerializer(recipe2)
        recipeSerializer3 = RecipeSerializer(recipe3)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(recipeSerializer1.data, res.data)
        self.assertNotIn(recipeSerializer2.data, res.data)
        self.assertIn(recipeSerializer3.data, res.data)


class ImageUploadTests(TestCase):
    """
    Tests for the image upload API.
    """

    def setUp(self):
        self.user = create_user(
            email='test@example.com',
            password='sampletest123'
        )
        self.recipe = create_recipe(self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def tearDown(self):
        self.recipe.image.delete()

    def test_upload_image(self):
        """
        Test uploading an image to a recipe.
        """
        url = image_upload_url(self.recipe.id)

        with tempfile.NamedTemporaryFile(suffix='.jpg') as image_file:
            img = Image.new('RGB', (10, 10))
            img.save(image_file, format='JPEG')
            image_file.seek(0)
            payload = {'image': image_file}
            res = self.client.post(url, payload, format='multipart')

        self.recipe.refresh_from_db()
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('image', res.data)
        self.assertTrue(os.path.exists(self.recipe.image.path))

    def test_upload_image_dab_request(self):
        """
        Test uploading invalid image.
        """
        url = image_upload_url(self.recipe.id)
        payload = {'image': 'notanimage'}
        res = self.client.post(url, payload, format='multipart')

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
