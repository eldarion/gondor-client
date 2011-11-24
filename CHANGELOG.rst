=========
CHANGELOG
=========

1.0.2 (dev)
===========

 * fixed sqldump to display stdout on stderr allowing it to be piped correctly

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
