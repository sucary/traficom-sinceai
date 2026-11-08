# Finland assessment boundary

`finland_assessment_boundary.geojson` combines official Finnish land-border and
territorial-sea outer-limit layers. It is not a coastline. The distinct features carry
the P.1546 screening zone used by the assessment (`Land` or `Cold`).

- Provider: National Land Survey of Finland
- Feature: `FI_AU_ADMINISTRATIVEUNIT_COUNTRY_FI`
- Layer: `au:AdministrativeUnit`
- CRS: EPSG:4326
- Licence: NLS open data attribution licence (CC BY 4.0)
- Retrieved: 2026-11-07
- Product description: https://www.maanmittauslaitos.fi/en/maps-and-spatial-data/datasets-and-interfaces/product-descriptions/division-administrative-areas-vector
- WFS documentation: https://www.maanmittauslaitos.fi/inspire-kyselypalvelut-wfs

The maritime feature comes from Traficom's `avoin:TerritorialSeaArea_L` layer:

- Provider: Finnish Transport and Communications Agency Traficom
- Layer: `avoin:TerritorialSeaArea_L`
- Licence: CC BY 4.0
- Retrieved: 2026-11-07
- WFS documentation: https://www.traficom.fi/fi/liikennejarjestelma/paikkatietoaineistot/rajapinnat

The normalization removes consecutive duplicate positions emitted by the WFS and
otherwise preserves the source coordinates. Rebuild it with:

```powershell
python backend/scripts/normalize_finland_assessment_boundary.py `
  tmp/border-data/nls-finland-state.geojson `
  tmp/border-data/territorial-sea.geojson `
  backend/src/app/reference/finland_assessment_boundary.geojson
```
