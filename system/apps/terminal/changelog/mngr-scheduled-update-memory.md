`test_a_theme_s_rules_leave_the_wrapper_page_as_it_is` expects the wrapper page's own background to be ttyd's `#2b2b2b`, not black.

The wrapper's `body` rule moved from `#000` to `#2b2b2b` on purpose, so the beat before ttyd opens its terminal reads as the terminal. The test still pinned the old black, so it failed on `main` for everyone. What the test is actually about -- that a theme's rules leave the wrapper alone -- is the comparison below it, and is unchanged.
