<#
.SYNOPSIS
Gets a Luxmed Patient Portal authorization token.

.DESCRIPTION
Calls /PatientPortal/Account/LogIn with login/password and returns the token
from the JSON response. Optional CookieHeader can be passed when Luxmed requires
browser/session/anti-bot cookies.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string] $Login = $env:LUXMED_LOGIN,

    [Parameter(Mandatory = $false)]
    [string] $Password = $env:LUXMED_PASSWORD,

    [Parameter(Mandatory = $false)]
    [string] $CookieHeader = $env:LUXMED_COOKIE_HEADER,

    [Parameter(Mandatory = $false)]
    [string] $BaseUri = "https://portalpacjenta.luxmed.pl",

    [Parameter(Mandatory = $false)]
    [string] $UserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",

    [Parameter(Mandatory = $false)]
    [switch] $DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Login)) {
    throw "Missing login. Pass -Login or set LUXMED_LOGIN."
}

if ([string]::IsNullOrWhiteSpace($Password)) {
    throw "Missing password. Pass -Password or set LUXMED_PASSWORD."
}

$uri = "{0}/PatientPortal/Account/LogIn" -f $BaseUri.TrimEnd("/")
$body = @{
    login = $Login
    password = $Password
} | ConvertTo-Json -Compress

$headers = @{
    "Accept" = "application/json, text/plain, */*"
    "Accept-Language" = "ru,en;q=0.9,be;q=0.8,pl;q=0.7"
    "Cache-Control" = "no-cache"
    "Origin" = $BaseUri.TrimEnd("/")
    "Pragma" = "no-cache"
    "Referer" = "{0}/PatientPortal/NewPortal/Page/Account/Login?returnUrl=%2FPage%2FReservation%2FResults" -f $BaseUri.TrimEnd("/")
    "User-Agent" = $UserAgent
    "X-Requested-With" = "XMLHttpRequest"
}

if (-not [string]::IsNullOrWhiteSpace($CookieHeader)) {
    $headers["Cookie"] = $CookieHeader
}

if ($DryRun) {
    [pscustomobject] @{
        Uri = $uri
        Method = "POST"
        HeaderNames = @($headers.Keys)
        BodyKeys = @("login", "password")
    }
    return
}

$response = Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -ContentType "application/json" -Body $body
if (-not $response.succeded -or [string]::IsNullOrWhiteSpace($response.token)) {
    $message = if ($response.errorMessage) { $response.errorMessage } else { "Login failed without errorMessage." }
    throw $message
}

$response.token
