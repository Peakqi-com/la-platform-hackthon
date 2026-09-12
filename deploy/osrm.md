# OSRM 台灣步行路網預處理（賽前做一次，產物放 data/osrm/）

```bash
mkdir -p data/osrm && cd data/osrm
wget https://download.geofabrik.de/asia/taiwan-latest.osm.pbf
docker run -t -v $PWD:/data osrm/osrm-backend osrm-extract -p /opt/foot.lua /data/taiwan-latest.osm.pbf
docker run -t -v $PWD:/data osrm/osrm-backend osrm-partition /data/taiwan-latest.osrm
docker run -t -v $PWD:/data osrm/osrm-backend osrm-customize /data/taiwan-latest.osrm
```

查詢：`GET http://osrm:5000/route/v1/foot/{lon1},{lat1};{lon2},{lat2}?overview=false` → `routes[0].distance`（公尺）。
產物約 1–2 GB，不進 git；上傳到 S3 或打成 release asset，EC2 user-data 再拉。
記憶體：foot profile 全台在 t3.small 可跑；t3.micro 會 OOM。
