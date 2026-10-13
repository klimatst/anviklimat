<?php
declare(strict_types=1);

// Defaults for a fresh local XAMPP installation. Change these values when
// connecting the site to a hosted or password-protected MySQL database.
return [
    'db_host' => 'localhost',
    'db_port' => 3306,
    'db_name' => 'klimaeco',
    'db_user' => 'root',
    'db_password' => '',
    // Empty means derive the install path from the current host and URL.
    'base_url' => '',
];
