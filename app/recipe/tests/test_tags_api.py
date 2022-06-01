"""
Test for the tags API.
"""

from decimal import Decimal


from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import TestCase

from rest_framework import status
from rest_framework.test import APIClient

from core.models import (
    Recipe,
    Tag,
)

from recipe.serializers import TagSerializer

TAGS_URL = reverse('recipe:tag-list')


def detail_url(tag_id):
    """
    Create and return a tag detail url.
    """
    return reverse('recipe:tag-detail', args=[tag_id])


def create_user(email='test@example.com', password='sampletest123'):
    """
    Create and return a new user.
    """
    return get_user_model().objects.create_user(email, password)


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


class PublicTagsApiTests(TestCase):
    """
    Test unauthenticated API requests.
    """

    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        """
        Test auth is required for retrieving tags.
        """
        res = self.client.get(TAGS_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateTagsApiTests(TestCase):
    """
    Test authenticated API request.
    """

    def setUp(self):
        self.user = create_user()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_retrieve_tags(self):
        """
        Test retrieving a list of tags.
        """
        Tag.objects.create(user=self.user, name='Vegan')
        Tag.objects.create(user=self.user, name='Dessert')

        res = self.client.get(TAGS_URL)

        tags = Tag.objects.all().order_by('-name')
        serializer = TagSerializer(tags, many=True)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_limited_to_user(self):
        """
        Test list of tags is limited to authenticated user.
        """
        other_user = create_user(
            email='bob@example.com', password='samplebob123')
        Tag.objects.create(user=other_user, name='Beverage')
        tag = Tag.objects.create(user=self.user, name='Chinese Food')

        res = self.client.get(TAGS_URL)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]['name'], tag.name)
        self.assertEqual(res.data[0]['id'], tag.id)

    def test_update_tag(self):
        """
        Test updating a tag.
        """
        tag = Tag.objects.create(user=self.user, name='Beverage')

        payload = {'name': 'Updated Beverage'}
        res = self.client.patch(detail_url(tag.id), payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        tag.refresh_from_db()
        self.assertEqual(tag.name, payload['name'])

    def test_delete_tag(self):
        """
        Test deleting a tag.
        """
        tag = Tag.objects.create(user=self.user, name='Beverage')

        res = self.client.delete(detail_url(tag.id))

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        tags = Tag.objects.filter(user=self.user)
        self.assertFalse(tags.exists())

    def test_filter_tags_assigned_to_recipes(self):
        """
        Test listing tags by those assigned to recipes.
        """
        tag1 = Tag.objects.create(user=self.user, name='Breakfast')
        tag2 = Tag.objects.create(user=self.user, name='Lunch')

        recipe = create_recipe(user=self.user, title='Rendang')
        recipe.tags.add(tag2)

        tagSerializer1 = TagSerializer(tag1)
        tagSerializer2 = TagSerializer(tag2)

        params = {
            'assigned_only': 1,
        }
        res = self.client.get(TAGS_URL, params)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertNotIn(tagSerializer1.data, res.data)
        self.assertIn(tagSerializer2.data, res.data)

    def test_filter_tags_unique(self):
        """
        Test filtered tags returns unique list.
        """
        tag = Tag.objects.create(user=self.user, name='Breakfast')
        Tag.objects.create(user=self.user, name='Dinner')

        recipe1 = create_recipe(user=self.user, title='Pancakes')
        recipe2 = create_recipe(user=self.user, title='Porridge')
        recipe1.tags.add(tag)
        recipe2.tags.add(tag)

        params = {
            'assigned_only': 1,
        }
        res = self.client.get(TAGS_URL, params)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)
