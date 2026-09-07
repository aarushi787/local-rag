function Assert-LocalPostgresTarget {
    param([Parameter(Mandatory = $true)][string]$ConnectionUrl)
    $target = $null
    if (-not [Uri]::TryCreate($ConnectionUrl, [UriKind]::Absolute, [ref]$target)) {
        throw 'Target must be an absolute PostgreSQL URL.'
    }
    if ($target.Scheme -notin @('postgresql', 'postgres') -or
        $target.Host -notin @('127.0.0.1', '[::1]', '::1', 'localhost') -or
        $target.Query -or $target.Fragment -or $target.AbsolutePath -eq '/') {
        throw 'Target must be a named loopback PostgreSQL database with no query overrides.'
    }
}
