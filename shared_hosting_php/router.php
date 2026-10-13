<?php
declare(strict_types=1);

/**
 * Development-server router used by START-LOCAL.cmd.
 * Apache deployments use the matching .htaccess protections instead.
 */
$requestPath = parse_url((string)($_SERVER['REQUEST_URI'] ?? '/'), PHP_URL_PATH);
$requestPath = is_string($requestPath) ? rawurldecode($requestPath) : '/';
if (str_contains($requestPath, "\0") || str_contains($requestPath, '\\')) {
    http_response_code(400);
    exit("Bad request\n");
}

$segments = array_values(array_filter(explode('/', $requestPath), static fn(string $part): bool => $part !== ''));
if (in_array('.', $segments, true) || in_array('..', $segments, true)) {
    http_response_code(404);
    exit("Not found\n");
}

$lowerSegments = array_map('strtolower', $segments);
$first = $lowerSegments[0] ?? '';
$second = $lowerSegments[1] ?? '';
$blocked = in_array($first, ['app', 'data', 'maintenance', '.git', '.github', 'router.php'], true)
    || ($first === 'storage' && $second !== 'uploads')
    || count(array_filter($segments, static fn(string $segment): bool => str_starts_with($segment, '.'))) > 0;

if ($first === 'storage' && $second === 'uploads') {
    $extension = strtolower(pathinfo((string)end($segments), PATHINFO_EXTENSION));
    if (in_array($extension, ['php', 'phtml', 'php3', 'php4', 'php5', 'phar'], true)) {
        $blocked = true;
    }
}

if ($first === 'install' && is_file(__DIR__ . '/app/config.php')) {
    $blocked = true;
}

if ($blocked) {
    http_response_code(404);
    header('Content-Type: text/plain; charset=utf-8');
    exit("Not found\n");
}

header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: strict-origin-when-cross-origin');
header('X-Frame-Options: SAMEORIGIN');
return false;
