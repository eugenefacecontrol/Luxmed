$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$session.UserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 YaBrowser/26.8.0.0 Safari/537.36"
$session.Cookies.Add((New-Object System.Net.Cookie("visid_incap_2214638", "x/gisRUgQEqAXteKMU6mn0K5QmkAAAAAQUIPAAAAAABxpEja5PYm1r37SuGawO+k", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("PatientPortalDeviceId", "4d7e1bda-0f88-455d-bf5b-de983f9fdee9", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("visid_incap_2269135", "TUM3Do+MTg+xYWwRJ172eb29Z2kAAAAAQUIPAAAAAAAaXwjcmvtSflDvAZE+Xt98", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("LXCookieMonit", "1", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("GlobalLang", "pl", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("PatientPortalCookieMonit", "1", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("incap_ses_688_2214638", "nC8cIeKcXTP4Um0nB0WMCTrWo2oAAAAA1K2rL9CTKGWu2TMKTeo1Fg==", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("_fbp", "fb.1.1789122108721.858050406310417169", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("OptanonAlertBoxClosed", "2026-09-11T10:21:49.766Z", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("_uetsid", "99a18490adca11f184a1837276f14a55", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("_uetvid", "99a1a3e0adca11f1a62e6d37fd6899b0", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("_gcl_au", "1.1.379540439.1789122110", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("_ga", "GA1.1.643747395.1789122110", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("_hjSessionUser_3382049", "eyJpZCI6IjM2MzQ2ZTViLTllNDEtNTJhOS1hYzFkLWUxOTY4MTgxOGI1YiIsImNyZWF0ZWQiOjE3ODkxMjIxMTAyNTcsImV4aXN0aW5nIjpmYWxzZX0=", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("OptanonConsent", "isGpcEnabled=0&datestamp=Fri+Sep+11+2026+12%3A21%3A50+GMT%2B0200+(Central+European+Summer+Time)&version=202606.2.0&browserGpcFlag=0&isDntEnabled=1&isIABGlobal=false&hosts=&consentId=906f6868-945e-4ee3-bf74-3d117823f798&interactionCount=1&isAnonUser=1&prevHadToken=0&landingPath=NotLandingPage&groups=C0001%3A1%2CC0003%3A1%2CC0004%3A1%2CC0002%3A1&fclco=&lastConsentTs=1789122109&intType=1&crTime=1789122110281", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("incap_ses_688_2269135", "h5PmO/HNO0uOWG0nB0WMCT/Wo2oAAAAAbzwre5MQYms32vS4gNFpyA==", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("__RequestVerificationToken_L1BhdGllbnRQb3J0YWw1", "2fYcKjv-GaBYJf7-iQF2jHmxLw0YkyUiyTgMMEiyqwCOLSQ851dEafAzOZo-bwLK8LkY9XJapbGhFT_AL-gPLvNYRJ_U71jT39w1XJevLlRgLMENxIPnll_ba4sFUfC942TLCZUMQQmNb2_RNi_I7Q2", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("_ga", "GA1.3.643747395.1789122110", "/", ".portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("_ga_DJZE3L4HSN", "GS2.1.s1789122108`$o1`$g0`$t1789122113`$j55`$l0`$h0", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("kampyle_userid", "8387-f6ba-5c35-7c14-6571-38b2-a921-e5e9", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("kampyleUserSession", "1789122113533", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("kampyleUserSessionsCount", "1", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("kampyleUserPercentile", "60.60724549113525", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("XSRF-TOKEN", "mg_5FxitRJHcRoqHnBprt4Fui2jFPxjEVQjriRU5380HZWHF3k7OAcaGTXXCuhlAOpLSYxzCv5q_i9tJnJzUu0AksadwE2aRARVHKEZ_h0RL5qLBkNZMbLA9dVjHNFWmxMej6GW0TAqohy39YRsevQ2", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("incap_ses_692_2269135", "DyBmUjtSgjAat3PBenqaCU/2o2oAAAAAgnwFAbh0GdfwyuWDGlA/gQ==", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("ASP.NET_SessionId", "antv1sxumq4irjgmhlcal0gs", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("RefreshToken", "a7ec5ae3-d611-477e-aca8-89bb8cbe3b5c", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("Authorization-Token", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzZXNzaW9uX2lkIjoiNWYzYTc5OTctYjUzNi00YTRkLWI3NTItMjlkZjJkYTA4MDczIiwidW5pcXVlX25hbWUiOiJ5YXVoZW5pc2hlaW1hQGdtYWlsLmNvbSIsImdpdmVuX25hbWUiOiJZQVVIRU5JIiwiZmFtaWx5X25hbWUiOiJTSEVJTUEiLCJnZW5kZXIiOiJNYWxlIiwiYmlydGhkYXRlIjoiODAxMDE0NDAwIiwicGhvbmVfbm8iOiI1NzIyMzA4NTEiLCJlbWFpbCI6InlhdWhlbmlzaGVpbWFAZ21haWwuY29tIiwibHhfcm9sZSI6IkJlbmVmaWNpYXJ5IiwibHdzIjoiRmFsc2UiLCJ2aXBfbGV2ZWwiOiIwIiwibWVkaWNhbF9jaGF0c19hY2MiOiJUcnVlIiwiaGFzX3Blc2VsIjoiVHJ1ZSIsImVuY29kZWRwYXRpZW50aWQiOiJSZW43WStRVUFlczUxNVJTWnZmWWgzWERwSndUSWlkQ0tPSjhYVHN1OXIyWmw4WTY0TllOSWRVR09tRzIrT0dTUmJpK3ZBUlRSR3dMTnI0bjR5THB2VFJibXh0cGdsV1p4ZmpOb2dUR3lZdz0iLCJyb2xlIjoiUmVnaXN0ZXJlZFVzZXIiLCJodHRwOi8vc2NoZW1hcy54bWxzb2FwLm9yZy93cy8yMDA1LzA1L2lkZW50aXR5L2NsYWltcy9zeXN0ZW0iOiIwIiwiYWNjb3VudGlkIjoiNjJhY2ZmMTUtMjNjOS00MjhkLWI3OGEtYzZhNDg0NTE1YjZkIiwibWZhZGV2aWNlc3RhdHVzIjoiVHJ1c3RlZCIsImlzX3RlY2huaWNhbF91c2VyIjoiRmFsc2UiLCJseF90b2tlbiI6ImMxNDVjMjBlLWZmNGMtNGNlNS04YzJkLWE4ODM1M2E0NzJlNiIsImx4X3NlZ21lbnRfaWQiOiIzIiwibWZhZGV2aWNlaWQiOiI0ZDdlMWJkYS0wZjg4LTQ1NWQtYmY1Yi1kZTk4M2Y5ZmRlZTkiLCJmZWF0dXJlX3RvZ2dsZSI6WyJDb3N0UmV0dXJuUHJvY2VzcyIsIkFjY2Vzc09ubGluZVBheW1lbnRzIiwiUE9aRGVjbGFyYXRpb25Qcm9jZXNzIiwiSW5ib3hNb2R1bGVBY2Nlc3MiLCJNb2JpbGVBY2Nlc3NPbmxpbmVQYXltZW50cyIsIk1lZGljYWxQYWNrYWdlVmVyaWZpY2F0aW9uTW9kdWxlIiwiV2ViU3VydmV5IiwiSGFzQWNjZXNzVG9OZXdEYXNoYm9hcmQiLCJSZWRpcmVjdENibVRlbGVtZWRpY2luZVRvRGVsb2NhbGl6ZWRTZWFyY2giLCJDQ1N2MkFjY2VzcyIsIlVzZU9jY3VwYXRpb25hbE1lZGljaW5lUmVzdEFwaSIsIlNob3dWaXNpdE1hbmFnZUJ1dHRvbnMiLCJEcnVnc0FwaUluQ29udGFpbmVyIiwiSGFzQWNjZXNzVG9NRkEiLCJEcnVnc05BSSIsIk5ld0hvcml6b25QYXltZW50cyIsIkRpZ2l0YWxDYXJlSHViRXh0cmFBY2Nlc3MiLCJEZW50YWwtRGlhZ3JhbSIsIlBOTVNlYXJjaCIsIlJlaGFiaWxpdGF0aW9uQXV0b0xvYWREYXlzIl0sIm5iZiI6MTc4OTEzMDMyNSwiZXhwIjoxNzg5MTMwOTI1LCJpYXQiOjE3ODkxMzAzMjUsImlzcyI6InBwLWlkIiwiYXVkIjoicHAtcHJkIn0.DTsparu7DTlC28KsT9Uc4S4sVivglpuBoqVsTW7PGEM", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("UserAdditionalInfo", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJVc2VyTXVzdEFjY2VwdFRlcm1zIjpmYWxzZSwiVXNlck11c3RVcGRhdGVDb250YWN0RGV0YWlscyI6ZmFsc2UsIlVzZXJNdXN0Q2hhbmdlUGFzc3dvcmQiOmZhbHNlLCJQYXRpZW50RGF0YVByb2Nlc3NpbmdDb25zZW50IjpmYWxzZSwiU2hvdWxkU2hvd09ibGlnYXRvcnlQb3B1cHMiOmZhbHNlLCJJc0VtYmVkZGVkTW9kZSI6ZmFsc2UsIklzT25CbGFja0xpc3QiOmZhbHNlLCJEZXZpY2VUcnVzdFN0YXR1cyI6MSwibmJmIjoxNzg5MTMwMzI1LCJleHAiOjE3ODkyMTY3MjUsImlhdCI6MTc4OTEzMDMyNX0.mxFR5_zxX3lZGjfaokFdS-0J2KPm1eh_q6OGhdbGXuA", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("LXToken", "c145c20e-ff4c-4ce5-8c2d-a88353a472e6", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("kampyleSessionPageCounter", "16", "/", "portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("_ga_033Y4WH47B", "GS2.1.s1789130321`$o2`$g1`$t1789130377`$j4`$l0`$h0", "/", ".luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("_ga_4HXC64PY92", "GS2.3.s1789130321`$o2`$g1`$t1789130377`$j4`$l0`$h0", "/", ".portalpacjenta.luxmed.pl")))
$session.Cookies.Add((New-Object System.Net.Cookie("nlbi_2269135", "hijfb7zAmH923WO6J6/DMAAAAAB2iXD9sfA1V+0MaBust723", "/", ".luxmed.pl")))


Invoke-WebRequest -UseBasicParsing -Uri "https://portalpacjenta.luxmed.pl/PatientPortal/NewPortal/terms/oneDayTerms?searchPlace.id=3&searchPlace.name=Krak%C3%B3w&searchPlace.type=0&serviceVariantId=4596&languageId=10&searchDateFrom=2026-09-22&searchDateTo=2026-09-22&referralId=372397537&referralTypeId=3&processId=93229d59-8725-426e-ae31-239b87424065&searchByMedicalSpecialist=false&expectedTermsNumber=1&delocalized=false" `
-WebSession $session `
-Headers @{
"authority"="portalpacjenta.luxmed.pl"
  "method"="GET"
  "path"="/PatientPortal/NewPortal/terms/oneDayTerms?searchPlace.id=3&searchPlace.name=Krak%C3%B3w&searchPlace.type=0&serviceVariantId=4596&languageId=10&searchDateFrom=2026-09-22&searchDateTo=2026-09-22&referralId=372397537&referralTypeId=3&processId=93229d59-8725-426e-ae31-239b87424065&searchByMedicalSpecialist=false&expectedTermsNumber=1&delocalized=false"
  "scheme"="https"
  "accept"="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
  "accept-encoding"="gzip, deflate, br, zstd"
  "accept-language"="ru,en;q=0.9,be;q=0.8,pl;q=0.7"
  "cache-control"="no-cache"
  "dnt"="1"
  "pragma"="no-cache"
  "priority"="u=0, i"
  "sec-ch-ua"="`"Not;A=Brand`";v=`"8`", `"Chromium`";v=`"150`", `"YaBrowser`";v=`"26.8`", `"Yowser`";v=`"2.5`""
  "sec-ch-ua-mobile"="?0"
  "sec-ch-ua-platform"="`"macOS`""
  "sec-fetch-dest"="document"
  "sec-fetch-mode"="navigate"
  "sec-fetch-site"="none"
  "sec-fetch-user"="?1"
  "upgrade-insecure-requests"="1"
}