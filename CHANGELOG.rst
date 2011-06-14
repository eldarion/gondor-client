=========
CHANGELOG
=========

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
