"""The deployed app installs requirements.txt and nothing else.

These tests keep scraper, data-job and test packages out of that file, and
check that the code the web app runs still works without them. CI also runs
this file in a job that really does install only requirements.txt.
"""

import importlib
import re
import sys
import tomllib
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.messages import get_messages

NOT_FOR_THE_WEB = {
    'selenium',
    'webdriver-manager',
    'chardet',
    'djangorestframework',
    'shapely',
    'pytest',
    'pytest-django',
    'pytest-cov',
    'pytest-mock',
    'factory-boy',
    'responses',
    'freezegun',
    'ruff',
}


def _requirements(name: str) -> dict[str, str]:
    """{package: line} for the pinned packages in a requirements file."""
    packages = {}
    for line in (settings.BASE_DIR / name).read_text().splitlines():
        line = line.split('#')[0].strip()
        if line and not line.startswith('-r'):
            packages[re.split(r'[=<>~!]', line, maxsplit=1)[0].strip().lower()] = line
    return packages


class TestRequirementFiles:
    def test_web_requirements_carry_no_scraper_or_test_packages(self):
        assert NOT_FOR_THE_WEB.isdisjoint(_requirements('requirements.txt'))

    def test_pyproject_lists_the_same_runtime_dependencies(self):
        """Vercel can build from either file, so they must not drift apart."""
        project = tomllib.loads((settings.BASE_DIR / 'pyproject.toml').read_text())['project']

        assert sorted(project['dependencies']) == sorted(_requirements('requirements.txt').values())
        assert sorted(project['optional-dependencies']['scrape']) == sorted(
            _requirements('requirements-scrape.txt').values()
        )

    def test_dev_requirements_pull_in_every_other_file(self):
        text = (settings.BASE_DIR / 'requirements-dev.txt').read_text()
        for name in ('requirements.txt', 'requirements-scrape.txt', 'requirements-data.txt'):
            assert f'-r {name}' in text

    def test_rest_framework_is_not_installed_as_an_app(self):
        assert 'rest_framework' not in settings.INSTALLED_APPS


@pytest.fixture
def scraper_without_selenium():
    """The scraper module as it loads where Selenium isn't installed."""
    import apps.analytics.tasks.pcpao_scraper as scraper

    hidden = {name: None for name in ('selenium', 'webdriver_manager', 'webdriver_manager.chrome')}
    hidden.update({name: None for name in list(sys.modules) if name.startswith('selenium.')})
    with patch.dict(sys.modules, hidden):
        yield importlib.reload(scraper)
    importlib.reload(scraper)


class TestScraperWithoutSelenium:
    def test_module_imports_and_says_selenium_is_missing(self, scraper_without_selenium):
        assert scraper_without_selenium.SELENIUM_AVAILABLE is False

    def test_requests_based_refresh_methods_are_still_there(self, scraper_without_selenium):
        scraper = scraper_without_selenium.PCPAOScraper(headless=True)

        assert callable(scraper._search_via_api)
        assert callable(scraper._scrape_detail_via_requests)

    def test_browser_scraper_explains_what_to_install(self, scraper_without_selenium):
        with pytest.raises(RuntimeError, match='requirements-scrape.txt'):
            scraper_without_selenium.PCPAOScraper(headless=True).setup_driver()


@pytest.mark.django_db
class TestRefreshDegradesGracefully:
    def test_refresh_says_so_when_the_scraper_cannot_be_imported(self, client, sample_property):
        url = f'/analytics/property/{sample_property.parcel_id}/refresh/'
        with patch.dict(sys.modules, {'apps.analytics.tasks.scrape_data': None}):
            response = client.post(url)

        assert response.status_code == 302
        assert f'/analytics/property/{sample_property.parcel_id}/?refreshed=' in response['Location']
        assert [str(message) for message in get_messages(response.wsgi_request)] == [
            "Refresh isn't available on this server. The data here is updated from the county's file every month."
        ]
