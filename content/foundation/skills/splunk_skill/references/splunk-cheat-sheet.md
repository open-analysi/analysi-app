# Splunk Cheat Sheet: Query, SPL, RegEx, & Commands

## Search Processing Language (SPL)

Commands are chained using the pipe `|` character:
```
search | command1 arguments1 | command2 arguments2 | ...
```

### Time Modifiers
Specify time ranges using `earliest` and `latest`:
```
"error earliest=-1d@d latest=h@h"
```

Relative time syntax: `[+|-]<integer><unit>@<snap_time_unit>`

### Subsearches
Run searches and return results as argument values in square brackets:
```
sourcetype=syslog [ search login error | return 1 user ]
```

### Search Optimization Tips
- Limit data pulled from disk to minimum
- Partition data into separate indexes by type
- Restrict time ranges (use `-1h` instead of `-1w`)
- Search specifically (`fatal_error` not `*error*`)
- Use post-processing searches in dashboards
- Use summary indexing and acceleration features

---

## Common Search Commands

| Command | Description |
|---------|-------------|
| **chart/timechart** | Tabular output for charting or time-series data |
| **dedup** | Removes subsequent results matching specified criteria |
| **eval** | Calculates expressions |
| **fields** | Removes fields from results |
| **head/tail** | Returns first/last N results |
| **lookup** | Adds field values from external sources |
| **rename** | Renames fields (supports wildcards) |
| **rex** | Extracts fields using regex named groups |
| **search** | Filters results matching search expression |
| **sort** | Sorts results by specified fields |
| **stats** | Provides aggregate statistics by grouped fields |
| **table** | Specifies fields to keep in tabular format |
| **top/rare** | Displays most/least common field values |
| **transaction** | Groups results into transactions |
| **where** | Filters using eval expressions |

---

## Common Eval Functions

| Function | Description | Example |
|----------|-------------|---------|
| **abs(X)** | Absolute value | `abs(number)` |
| **case(X,"Y",...)** | Boolean expression pairs | `case(error==404,"Not found",error==500,"Server Error")` |
| **ceil(X)** | Ceiling value | `ceil(1.9)` |
| **cidrmatch("X",Y)** | IP subnet matching | `cidrmatch("123.132.32.0/25",ip)` |
| **coalesce(X,...)** | First non-null value | `coalesce(null(),"Returned val",null())` |
| **cos(X)** | Cosine calculation | `n=cos(0)` |
| **exp(X)** | Returns e^X | `exp(3)` |
| **if(X,Y,Z)** | Conditional: true=Y, false=Z | `if(error==200,"OK","Error")` |
| **in(field,valuelist)** | Match value in list | `if(in(status,"404","500"),"true","false")` |
| **isbool/isint/isstr/isnull(X)** | Type checking | `isbool(field)` |
| **len(X)** | String character length | `len(field)` |
| **like(X,"Y")** | SQLite pattern matching | `like(field,"addr%")` |
| **log(X,Y)** | Logarithm with base Y | `log(number,2)` |
| **lower(X)** | Lowercase string | `lower(username)` |
| **ltrim/rtrim(X,Y)** | Trim characters from sides | `ltrim(" ZZZabcZZ "," Z")` |
| **match(X,Y)** | Regex pattern matching | `match(field,"^\\d{1,3}\\.\\d$")` |
| **max/min(X,...)** | Maximum/minimum values | `max(delay,mydelay)` |
| **md5(X)** | MD5 hash | `md5(field)` |
| **mvcount(X)** | Multi-valued field count | `mvcount(multifield)` |
| **mvfilter(X)** | Filter multi-valued fields | `mvfilter(match(email,"net$"))` |
| **mvindex(X,Y,Z)** | Multi-valued field subset | `mvindex(multifield,2)` |
| **mvjoin(X,Y)** | Join multi-valued with delimiter | `mvjoin(address,";")` |
| **now()** | Current Unix time | `now()` |
| **null()** | Returns NULL | `null()` |
| **random()** | Pseudo-random number | `random()` |
| **relative_time(X,Y)** | Apply relative time to epoch | `relative_time(now(),"-1d@d")` |
| **replace(X,Y,Z)** | Regex substitution | `replace(date,"^(\\d{1,2})/(\\d{1,2})/","\\2/\\1/")` |
| **round(X,Y)** | Round to decimal places | `round(3.5)` |
| **split(X,"Y")** | Split into multi-valued field | `split(address,";")` |
| **sqrt(X)** | Square root | `sqrt(9)` |
| **strftime(X,Y)** | Format epoch time | `strftime(_time,"%H:%M")` |
| **strptime(X,Y)** | Parse time string | `strptime(timeStr,"%H:%M")` |
| **substr(X,Y,Z)** | Substring extraction | `substr("string",1,3)` |
| **tonumber/tostring(X,Y)** | Type conversion | `tonumber("0A4",16)` |
| **typeof(X)** | Return field type | `typeof(12)` |
| **urldecode(X)** | URL decode | `urldecode("http%3A%2F%2Fwww.splunk.com")` |

---

## Common Stats Functions

| Function | Description |
|----------|-------------|
| **avg(X)** | Average of field values |
| **count(X)** | Occurrence count of field |
| **dc(X)** | Distinct value count |
| **earliest(X)** | Chronologically earliest value |
| **latest(X)** | Chronologically latest value |
| **max(X)** | Maximum value |
| **median(X)** | Middle-most value |
| **min(X)** | Minimum value |
| **mode(X)** | Most frequent value |
| **perc<X>(Y)** | X-th percentile of Y |
| **range(X)** | Difference between max and min |
| **stdev(X)** | Sample standard deviation |
| **stdevp(X)** | Population standard deviation |
| **sum(X)** | Sum of values |
| **sumsq(X)** | Sum of squares |
| **values(X)** | List of distinct values |
| **var(X)** | Sample variance |

---

## Regular Expressions (RegEx)

| Pattern | Meaning | Example |
|---------|---------|---------|
| `\s` | Whitespace | `\d\s\d` → digit space digit |
| `\S` | Non-whitespace | `\d\S\d` → digit non-ws digit |
| `\d` | Digit | `\d\d\d-\d\d-\d\d\d\d` → SSN |
| `\D` | Non-digit | `\D\D\D` → three non-digits |
| `\w` | Word character | `\w\w\w` → three word chars |
| `\W` | Non-word character | `\W\W\W` → three non-word chars |
| `[...]` | Any included character | `[a-z0-9#]` → chars a-z, 0-9, or # |
| `[^...]` | Excluded characters | `[^xyz]` → any char except x, y, z |
| `*` | Zero or more | `\w*` → zero or more word chars |
| `+` | One or more | `\d+` → integer |
| `?` | Zero or one | `\d\d\d-?\d\d-?\d\d\d\d` → SSN optional dashes |
| `\|` | OR operator | `\w\|\d` → word or digit |
| `(?P<var>...)` | Named extraction | `(?P<ssn>\d\d\d-\d\d-\d\d\d\d)` |
| `(?:...)` | Grouping | `(?:[a-zA-Z]\|\d)` → letter or digit |
| `^` | Line start | `^\d+` → line begins with digit |
| `$` | Line end | `\d+$` → line ends with digit |
| `{...}` | Repetition count | `\d{3,5}` → 3-5 digits |
| `\\` | Escape character | `\\\[` → escape bracket |

---

## Search Examples

### Filter Results
```
sourcetype=access_combined error | search status=404
```

### Group Results
```
... | transaction host cookie maxspan=30s maxpause=5s
```

```
... | transaction clientip startswith="signon" endswith="purchase"
```

### Order Results
```
... | head 20
... | reverse
... | sort ip, -url
... | tail 20
```

### Reporting
```
... | chart max(delay) over foo by bar
... | stats count by host
... | stats sparkline count by host
... | timechart count by host
... | timechart span=1m avg(CPU) by host
... | stats avg(*lay) by date_hour
... | top limit=20 url
... | rare url
```

### Advanced Reporting
```
... | eventstats avg(duration) as avgdur
... | streamstats sum(bytes) as bytes_total | timechart max(bytes_total)
sourcetype=nasdaq earliest=-10y | anomalydetection Close_Price
... | timechart count | predict count
... | timechart count | trendline sma5(count) as smoothed_count
```

### Add Fields
```
... | eval velocity=distance/time
... | rex field=_raw "From: (?<from>.*) To: (?<to>.*)"
... | accum count as total_count
... | delta count as countdiff
```

### Filter Fields
```
... | fields + host, ip
... | fields - host, ip
```

### Lookup Tables
```
... | lookup usertogroup user output group
... | inputlookup usertogroup
... | outputlookup users.csv
```

### Modify Fields
```
... | rename _ip as IPAddress
```

---

## Multi-Valued Fields

```
... | nomv recipients
... | makemv delim="," recipients | top recipients
... | mvexpand recipients
... | eval to_count = mvcount(recipients)
... | eval recipient_first = mvindex(recipient,0)
... | eval netorg_recipients = mvfilter(match(recipient,"\\.net$") OR match(recipient,"\\.org$"))
... | eval orgindex = mvfind(recipient,"\\.org$")
```

---

## Date and Time Formatting

### Time Components
- `%H` → 24-hour format (00-23)
- `%I` → 12-hour format (01-12)
- `%M` → Minute (00-59)
- `%S` → Second (00-61)
- `%N` → Subseconds (%3N=ms, %6N=μs, %9N=ns)
- `%p` → AM/PM
- `%Z` → Time zone (EST)
- `%z` → UTC offset (+hhmm or -hhmm)
- `%s` → Seconds since 1/1/1970

### Day Components
- `%d` → Day of month (01-31)
- `%j` → Day of year (001-366)
- `%w` → Weekday (0-6)
- `%a` → Abbreviated weekday (Sun)
- `%A` → Full weekday (Sunday)

### Month and Year
- `%b` → Abbreviated month (Jan)
- `%B` → Full month (January)
- `%m` → Month number (01-12)
- `%y` → Year without century (00-99)
- `%Y` → Full year (2021)

### Format Examples
- `%Y-%m-%d` → 2026-04-26
- `%y-%m-%d` → 21-12-31
- `%b %d, %Y` → Jan 24, 2021
- `%B %d, %Y` → January 24, 2021
