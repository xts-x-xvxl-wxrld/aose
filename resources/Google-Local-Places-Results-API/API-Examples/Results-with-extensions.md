https://serpapi.com/search.json?engine=google_local&q=health+service&location=Austin,+Texas,+United+States

import serpapi

client = serpapi.Client(api_key="cf64b18a88fd6fe68934e0ecd45378a39954d0b2349036711faef465f18db16a")
results = client.search({
  "engine": "google_local",
  "q": "health service",
  "location": "Austin, Texas, United States"
})
local_results = results["local_results"]

{
  "local_results": [
    ...
    {
      "position": 19,
      "rating": 3.0,
      "reviews_original": "(2)",
      "reviews": 2,
      "place_id": "6279182528142398096",
      "place_id_search": "https://serpapi.com/search.json?device=desktop&engine=google_local&gl=us&google_domain=google.com&hl=en&ludocid=6279182528142398096&q=private+health+service+in+austin",
      "provider_id": "/m/04g3gxf",
      "lsig": "AB86z5WaScbiSb4mZsqYMrTBQ6ws",
      "gps_coordinates": {
        "latitude": 30.273577600000003,
        "longitude": -97.7006447
      },
      "links": {
        "website": "https://lonestarcares.org/",
        "directions": "https://www.google.com/maps/dir//Lone+Star+Circle+of+Care+at+Oak+Springs,+3000+Oak+Springs+Dr+Suite+200,+Austin,+TX+78702/data=!4m6!4m5!1m1!4e2!1m2!1m1!1s0x8644b57581278a93:0x5724233da5c45290?sa=X&ved=2ahUKEwil2IS9gMqAAxWrh-4BHeQ9C2kQ48ADegQIBhAA&hl=en&gl=us"
      },
      "title": "Lone Star Circle of Care at Oak Springs",
      "type": "Medical clinic",
      "address": "3000 Oak Springs Dr Suite 200",
      "phone": "(877) 800-5722",
      "hours": "Closed ⋅ Opens 8 AM",
      "extensions": [
        "Medicare/Medicaid accepted",
        "Free or low-cost care",
        "Has online care"
      ]
    },
    {
      "position": 20,
      "rating": 3.6,
      "reviews_original": "(700)",
      "reviews": 700,
      "place_id": "1180798402976466894",
      "place_id_search": "https://serpapi.com/search.json?device=desktop&engine=google_local&gl=us&google_domain=google.com&hl=en&ludocid=1180798402976466894&q=private+health+service+in+austin",
      "provider_id": "/g/11fk1qdxcx",
      "lsig": "AB86z5WwMuiF4PHmzgSmYGJ9Plzj",
      "gps_coordinates": {
        "latitude": 30.27651,
        "longitude": -97.73383520000002
      },
      "links": {
        "website": "https://healthcare.ascension.org/Locations/Texas/TXAUS/Austin-Dell-Seton-Medical-Center-at-The-University-of-Texas?utm_campaign=gmb&utm_medium=organic&utm_source=local",
        "directions": "https://www.google.com/maps/dir//Dell+Seton+Medical+Ctr+at+The+Univ+of+Texas,+1500+Red+River+St,+Austin,+TX+78701/data=!4m6!4m5!1m1!4e2!1m2!1m1!1s0x8644b5a27ba55557:0x106309e430c2c7ce?sa=X&ved=2ahUKEwil2IS9gMqAAxWrh-4BHeQ9C2kQ48ADegQICRAA&hl=en&gl=us"
      },
      "title": "Dell Seton Medical Center at The University of Texas",
      "type": "Hospital",
      "address": "1500 Red River St",
      "phone": "(512) 324-7000",
      "hours": "Open 24 hours",
      "extensions": [
        "Medicare/Medicaid accepted",
        "Has online care"
      ]
    }
  ],
  ...
}
