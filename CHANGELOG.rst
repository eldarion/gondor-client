=========
CHANGELOG
=========

1.1 (dev)
=========

 * added --upgrade to init to perform a configuration upgrade
 * changed configuration format from INI to YAML (~/.gondor can remain in INI format)
 * added --no-on-deploy to deploy command which will prevent running of
   on_deploy commands
 * improved run to use the new interactive process on Gondor

1.0.6
=====

 * improved path handling of file argument to database:load
 * fixed formatting of errors when deploying
 * gondor run no longer needs -- to delimit run options from command options
 * fixed bug on Python 2.6 in database:load

1.0.5
=====

 * fixed bug introduced in 1.0.4 with manage commands other than database:load

1.0.4
=====

 * stablized database:load allowing SQL dumps to be uploaded
 * added gondor dashboard [instance] enabling quick opening of dashboard for site or instance

1.0.3
=====

 * added [app] managepy for customization the location of manage.py
 * added [app] local_settings when set to on will tell Gondor to not write a
   local_settings.py file; this is not fully supported on Gondor yet (full
   announcement coming soon)

1.0.2
=====

 * fixed sqldump to display stdout on stderr allowing it to be piped correctly
 * added gondor env and env:set to view and set instance environment variables
 * removed undocumented files.include functionality in favor of gondor env
 * added -v/--verbose for increasing verbosity level
 * default verbosity level makes "Reading from configuration... [ok]" hidden by default
 * added [app] compressor which enables running compress (from django_compressor) during deployment
 * removed checks on project layout (fixes Django 1.4 support) and paves way for more flexible layouts

1.0.1
=====

 * added gondor open to open an instance URL in your browser
 * removed deprecated API endpoint URLs
 * added [app] settings_module to allow overriding of DJANGO_SETTINGS_MODULE
 * added ability to store site_key in .gondor/site_key file (thanks Travis Swicegood)

1.0
===

 * no changes since post14

1.0b1.post14
============

 * changed requirements_file and wsgi_entry_point defaults to be more understood
 * added site_media_url default (has been supported for a while, but now added with init)
 * reworked configuration; allowing auth to be defined locally or globally
 * added support for API keys
 * improved how API errors are displayed
 * Gondor API now will force all users to use this version or newer

1.0b1.post13
============

 * fixed gondor manage when a task is not returned
 * removed use of a deprecated return value from API
 * changed gondor run to work with new API method of returning command output
 * Gondor API now will force all users to use this version or newer

1.0b1.post12
============

 * fixed a bug introduced in the PATH lookup changes in post11

1.0b1.post11
============

 * improved PATH lookups for git and hg (better Windows support)
 * improved wsgi_entry_point comment in INI

1.0b1.post10
============

 * added [app] site_media_url for overriding nginx site media URL

1.0b1.post9
===========

 * added warning about repo root being same as project root

1.0b1.post8 (the Donald Stufft release)
=======================================

 * added Windows support (thanks Donald Stufft!)
 * added [app] include option for added untracked files to tarball pushed to
   Gondor (thanks Donald Stufft again!)

1.0b1.post7
===========

 * check git revs for existence to fix "unable to read tarball: empty file"
   errors

1.0b1.post6
===========

 * added more information when running gondor init

1.0b1.post5
===========

 * corrected wording introduced in b1.post3 which was incorrect in a
   .gondor/config comment

1.0b1.post4
===========

 * when API returns non-200 responses show them more gracefully for better
   debugging (temporary fix until client gets refactored)

1.0b1.post3
===========

 * improved .gondor/config to include comments

1.0b1.post2
===========

 * added a way to display errors from new API (client soon to be updated to
   support everything nicely)
 * display URL on every deploy and in list
 * added staticfiles option to [app]; allowing values "on" or "off"
 * improved create success message regarding how to deploy to be friendly to
   all supported vcs users


1.0b1.post1
===========

 * removed internal Eldarion URL which could cause pip to ask for
   username/password when trying to install


1.0b1
=====

 * initial public release of Gondor client
