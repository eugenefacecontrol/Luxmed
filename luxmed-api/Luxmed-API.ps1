<#
.SYNOPSIS
Searches Luxmed Patient Portal appointment terms.

.DESCRIPTION
This script is a reusable version of a browser-exported request.

Required auth:
- Authorization-Token cookie value from an authenticated Luxmed Patient Portal session.

Usually optional, but useful when Luxmed rejects a copied request:
- XSRF-TOKEN
- RefreshToken
- LXToken
- PatientPortalDeviceId
- Incapsula cookies, passed via -CookieHeader or -ExtraCookies

The easiest flow is to log in via browser, copy the request's Cookie header
from DevTools, and pass it as -CookieHeader. The script extracts the important
cookies and ignores analytics/marketing noise.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string] $AuthorizationToken = $env:LUXMED_AUTHORIZATION_TOKEN,

    [Parameter(Mandatory = $false)]
    [string] $CookieHeader = $env:LUXMED_COOKIE_HEADER,

    [Parameter(Mandatory = $false)]
    [string] $XsrfToken = $env:LUXMED_XSRF_TOKEN,

    [Parameter(Mandatory = $false)]
    [string] $RefreshToken = $env:LUXMED_REFRESH_TOKEN,

    [Parameter(Mandatory = $false)]
    [string] $LxToken = $env:LUXMED_LX_TOKEN,

    [Parameter(Mandatory = $false)]
    [string] $PatientPortalDeviceId = $env:LUXMED_DEVICE_ID,

    [Parameter(Mandatory = $false)]
    [hashtable] $ExtraCookies = @{},

    [Parameter(Mandatory = $false)]
    [int] $SearchPlaceId = 3,

    [Parameter(Mandatory = $false)]
    [string] $SearchPlaceName = "Kraków",

    [Parameter(Mandatory = $false)]
    [int] $SearchPlaceType = 0,

    [Parameter(Mandatory = $false)]
    [int] $ServiceVariantId = 4448,

    [Parameter(Mandatory = $false)]
    [int] $LanguageId = 10,

    [Parameter(Mandatory = $false)]
    [datetime] $DateFrom = "2026-09-11",

    [Parameter(Mandatory = $false)]
    [datetime] $DateTo = "2026-09-23",

    [Parameter(Mandatory = $false)]
    [int] $SearchDatePreset = 13,

    [Parameter(Mandatory = $false)]
    [long] $ReferralId = 361815294,

    [Parameter(Mandatory = $false)]
    [int] $ReferralTypeId = 3,

    [Parameter(Mandatory = $false)]
    [string] $ProcessId = "0051045f-4f82-41de-bfa0-f5cbff5f3fab",

    [Parameter(Mandatory = $false)]
    [bool] $NextSearch = $false,

    [Parameter(Mandatory = $false)]
    [bool] $SearchByMedicalSpecialist = $false,

    [Parameter(Mandatory = $false)]
    [int] $ServiceVariantSource = 0,

    [Parameter(Mandatory = $false)]
    [bool] $LocationReplaced = $false,

    [Parameter(Mandatory = $false)]
    [bool] $Delocalized = $false,

    [Parameter(Mandatory = $false)]
    [string] $BaseUri = "https://portalpacjenta.luxmed.pl",

    [Parameter(Mandatory = $false)]
    [string] $UserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",

    [Parameter(Mandatory = $false)]
    [switch] $DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function ConvertFrom-CookieHeader {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Header
    )

    $cookies = @{}
    foreach ($part in ($Header -split ';')) {
        $trimmed = $part.Trim()
        if (-not $trimmed) {
            continue
        }

        $name, $value = $trimmed -split '=', 2
        if ($name -and $null -ne $value) {
            $cookies[$name.Trim()] = $value.Trim()
        }
    }

    return $cookies
}

function Add-Cookie {
    param(
        [Parameter(Mandatory = $true)]
        [Microsoft.PowerShell.Commands.WebRequestSession] $Session,

        [Parameter(Mandatory = $true)]
        [string] $Name,

        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string] $Value,

        [Parameter(Mandatory = $false)]
        [string] $Domain = "portalpacjenta.luxmed.pl"
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return
    }

    $Session.Cookies.Add([System.Net.Cookie]::new($Name, $Value, "/", $Domain))
}

function ConvertTo-LuxmedBoolean {
    param(
        [Parameter(Mandatory = $true)]
        [bool] $Value
    )

    return $Value.ToString().ToLowerInvariant()
}

$cookiesFromHeader = @{}
if (-not [string]::IsNullOrWhiteSpace($CookieHeader)) {
    $cookiesFromHeader = ConvertFrom-CookieHeader -Header $CookieHeader
}

if ([string]::IsNullOrWhiteSpace($AuthorizationToken) -and $cookiesFromHeader.ContainsKey("Authorization-Token")) {
    $AuthorizationToken = $cookiesFromHeader["Authorization-Token"]
}

if ([string]::IsNullOrWhiteSpace($AuthorizationToken)) {
    throw "Missing Authorization-Token. Pass -AuthorizationToken or set LUXMED_AUTHORIZATION_TOKEN / LUXMED_COOKIE_HEADER."
}

if ([string]::IsNullOrWhiteSpace($XsrfToken) -and $cookiesFromHeader.ContainsKey("XSRF-TOKEN")) {
    $XsrfToken = $cookiesFromHeader["XSRF-TOKEN"]
}

if ([string]::IsNullOrWhiteSpace($RefreshToken) -and $cookiesFromHeader.ContainsKey("RefreshToken")) {
    $RefreshToken = $cookiesFromHeader["RefreshToken"]
}

if ([string]::IsNullOrWhiteSpace($LxToken) -and $cookiesFromHeader.ContainsKey("LXToken")) {
    $LxToken = $cookiesFromHeader["LXToken"]
}

if ([string]::IsNullOrWhiteSpace($PatientPortalDeviceId) -and $cookiesFromHeader.ContainsKey("PatientPortalDeviceId")) {
    $PatientPortalDeviceId = $cookiesFromHeader["PatientPortalDeviceId"]
}

$session = [Microsoft.PowerShell.Commands.WebRequestSession]::new()
$session.UserAgent = $UserAgent

Add-Cookie -Session $session -Name "Authorization-Token" -Value $AuthorizationToken
Add-Cookie -Session $session -Name "XSRF-TOKEN" -Value $XsrfToken
Add-Cookie -Session $session -Name "RefreshToken" -Value $RefreshToken
Add-Cookie -Session $session -Name "LXToken" -Value $LxToken
Add-Cookie -Session $session -Name "PatientPortalDeviceId" -Value $PatientPortalDeviceId

$passthroughCookieNames = @(
    "ASP.NET_SessionId",
    "__RequestVerificationToken_L1BhdGllbnRQb3J0YWw1",
    "incap_ses_688_2269135",
    "incap_ses_692_2269135",
    "nlbi_2269135",
    "visid_incap_2269135"
)

foreach ($name in $passthroughCookieNames) {
    if ($cookiesFromHeader.ContainsKey($name)) {
        $domain = if ($name -match '^(incap_|nlbi_|visid_)') { ".luxmed.pl" } else { "portalpacjenta.luxmed.pl" }
        Add-Cookie -Session $session -Name $name -Value $cookiesFromHeader[$name] -Domain $domain
    }
}

foreach ($name in $ExtraCookies.Keys) {
    Add-Cookie -Session $session -Name $name -Value ([string] $ExtraCookies[$name])
}

$query = [ordered] @{
    "searchPlace.id" = $SearchPlaceId
    "searchPlace.name" = $SearchPlaceName
    "searchPlace.type" = $SearchPlaceType
    "serviceVariantId" = $ServiceVariantId
    "languageId" = $LanguageId
    "searchDateFrom" = $DateFrom.ToString("yyyy-MM-dd")
    "searchDateTo" = $DateTo.ToString("yyyy-MM-dd")
    "searchDatePreset" = $SearchDatePreset
    "referralId" = $ReferralId
    "referralTypeId" = $ReferralTypeId
    "processId" = $ProcessId
    "nextSearch" = ConvertTo-LuxmedBoolean -Value $NextSearch
    "searchByMedicalSpecialist" = ConvertTo-LuxmedBoolean -Value $SearchByMedicalSpecialist
    "serviceVariantSource" = $ServiceVariantSource
    "locationReplaced" = ConvertTo-LuxmedBoolean -Value $LocationReplaced
    "delocalized" = ConvertTo-LuxmedBoolean -Value $Delocalized
}

$queryString = ($query.GetEnumerator() | ForEach-Object {
    "{0}={1}" -f [uri]::EscapeDataString($_.Key), [uri]::EscapeDataString([string] $_.Value)
}) -join "&"

$uri = "{0}/PatientPortal/NewPortal/terms/index?{1}" -f $BaseUri.TrimEnd('/'), $queryString

$headers = @{
    "Accept" = "application/json, text/plain, */*"
    "Accept-Language" = "ru,en;q=0.9,be;q=0.8,pl;q=0.7"
    "Cache-Control" = "no-cache"
    "Pragma" = "no-cache"
    "Referer" = "{0}/PatientPortal/NewPortal/Page/Reservation/Results" -f $BaseUri.TrimEnd('/')
    "X-Requested-With" = "XMLHttpRequest"
}

if (-not [string]::IsNullOrWhiteSpace($XsrfToken)) {
    $headers["X-XSRF-TOKEN"] = $XsrfToken
}

if ($DryRun) {
    [pscustomobject] @{
        Uri = $uri
        CookieNames = @($session.Cookies.GetCookies([uri] $BaseUri).Name)
        HeaderNames = @($headers.Keys)
    }
    return
}

Invoke-WebRequest -UseBasicParsing -Method Get -Uri $uri -WebSession $session -Headers $headers
