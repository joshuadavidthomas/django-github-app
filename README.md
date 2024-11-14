<!-- docs-intro-begin -->
# django-github-app

[![PyPI](https://img.shields.io/pypi/v/django-github-app)](https://pypi.org/project/django-github-app/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/django-github-app)
![Django Version](https://img.shields.io/badge/django-4.2%20%7C%205.0%20%7C%205.1-%2344B78B?labelColor=%23092E20)
<!-- https://shields.io/badges -->
<!-- django-4.2 | 5.0 | 5.1-#44B78B -->
<!-- labelColor=%23092E20 -->

<!-- docs-intro-end -->

## Requirements

- Python 3.10, 3.11, 3.12, 3.13
- Django 4.2, 5.0, 5.1

## Installation

1. Register a new GitHub App, following [these instructions](https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app) from the GitHub Docs. For a more detailed tutorial, there is also [this page](https://docs.github.com/en/apps/creating-github-apps/writing-code-for-a-github-app/building-a-github-app-that-responds-to-webhook-events) -- in particular the section on [Setup](https://docs.github.com/en/apps/creating-github-apps/writing-code-for-a-github-app/building-a-github-app-that-responds-to-webhook-events#setup).

   Make note of the following information while setting up your new GitHub App:

    - App ID
    - Client ID
    - Name
    - Private Key (either the file object itself or the actual text)
    - Webhook Secret

2. Install the package from PyPI:

    ```bash
    python -m pip install django-github-app

    # or if you like the new hotness

    uv add django-github-app
    uv sync
    ```

3. Add the app to your Django project's `INSTALLED_APPS`:

    ```python
    INSTALLED_APPS = [
        ...,
        "django_github_app",
        ...,
    ]
    ```

4. Add the following dictionary to your Django project's `DJANGO_SETTINGS_MODULE`, filling in the values from step 1 above. The example below uses [environs](https://github.com/sloria/environs) to load the values from an `.env` file.

    ```python
    import environs
    
    env = environs.Env()
    env.read_env()

    GITHUB_APP = {
        "APP_ID": env.int("GITHUB_APP_ID"),
        "CLIENT_ID": env.str("GITHUB_CLIENT_ID"),
        "NAME": env.str("GITHUB_NAME"),
        "PRIVATE_KEY": env.str("GITHUB_PRIVATE_KEY"),
        "WEBHOOK_SECRET": env.str("GITHUB_WEBHOOK_SECRET"),
    }
    ```

   > [!NOTE]
   >
   > In this example, the private key's contents are set and loaded directly from the environment. If you prefer to use the file itself, you could do something like this instead:
   >
   > ```python
   > from pathlib import Path
   > 
   > GITHUB_APP = {
   >     ...
   >     "PRIVATE_KEY": Path(env.path("GITHUB_PRIVATE_KEY_PATH")).read_text(),
   >     ...
   > }
   > ```

## Getting Started

## Documentation

Please refer to the [documentation](https://django-github-app.readthedocs.io) for more information.

## License

django-github-app is licensed under the MIT license. See the [`LICENSE`](LICENSE) file for more information.
