import pytest
from apps.KeywordSelection.models import Keyword

pytestmark = pytest.mark.django_db


class TestKeywordModel:
    def test_create_keyword(self, db):
        """Test that a Keyword can be created with valid data."""
        keyword = Keyword.objects.create(
            name='City',
            data_type='select',
            help_text='Select a city',
            priority=1,
            is_active=True,
            listing_field='city',
            extra_json={'choices': ['Clearwater', 'St Petersburg']},
        )
        assert keyword.pk is not None
        assert keyword.name == 'City'

    def test_keyword_ordering_by_priority(self, db):
        """Test keywords are ordered by priority."""
        Keyword.objects.create(name='Second', priority=2, is_active=True)
        Keyword.objects.create(name='First', priority=1, is_active=True)
        Keyword.objects.create(name='Third', priority=3, is_active=True)

        keywords = list(Keyword.objects.all().order_by('priority'))
        assert keywords[0].name == 'First'
        assert keywords[1].name == 'Second'
        assert keywords[2].name == 'Third'

    def test_extra_json_field(self, db):
        """Test JSONField stores complex data correctly."""
        keyword = Keyword.objects.create(
            name='Price Range',
            data_type='range',
            extra_json={
                'min': 0,
                'max': 1000000,
                'step': 10000,
                'format': 'currency',
            },
        )
        keyword.refresh_from_db()
        assert keyword.extra_json['min'] == 0
        assert keyword.extra_json['format'] == 'currency'

    def test_is_active_filter(self, db):
        """Test filtering by is_active flag."""
        Keyword.objects.create(name='Active', is_active=True)
        Keyword.objects.create(name='Inactive', is_active=False)

        active = Keyword.objects.filter(is_active=True)
        assert active.count() == 1
        assert active.first().name == 'Active'

    def test_str_representation(self, db):
        """Test __str__ returns name and priority."""
        keyword = Keyword.objects.create(
            name='TestKeyword',
            priority=5,
        )
        str_repr = str(keyword)
        assert 'TestKeyword' in str_repr
        assert '5' in str_repr

    def test_default_data_type(self, db):
        """Test default data_type is 'text'."""
        keyword = Keyword.objects.create(name='DefaultType')
        assert keyword.data_type == 'text'

    def test_default_priority_is_zero(self, db):
        """Test default priority is 0."""
        keyword = Keyword.objects.create(name='DefaultPriority')
        assert keyword.priority == 0

    def test_default_is_active_is_true(self, db):
        """Test default is_active is True."""
        keyword = Keyword.objects.create(name='DefaultActive')
        assert keyword.is_active is True

    def test_default_extra_json_is_empty_dict(self, db):
        """Test default extra_json is empty dict."""
        keyword = Keyword.objects.create(name='DefaultJson')
        assert keyword.extra_json == {}

    def test_unique_name_constraint(self, db):
        """Test unique name constraint."""
        from django.db import IntegrityError

        Keyword.objects.create(name='Unique')
        with pytest.raises(IntegrityError):
            Keyword.objects.create(name='Unique')
