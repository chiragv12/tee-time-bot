from zoneinfo import ZoneInfo

# MVP scope is fairfax-county-mco only, which is Eastern-time courses.
SITE_TIMEZONE = ZoneInfo("America/New_York")

# No clean API for this — TeeItUp's own name lookup is a Next.js RSC-format page fetch,
# not a plain JSON endpoint. Names are static, so maintaining them here is simpler.
FACILITY_NAMES = {
    7743: "Twin Lakes Golf Course - Lakes Course",
    7756: "Twin Lakes Golf Course - Oaks Course",
}
