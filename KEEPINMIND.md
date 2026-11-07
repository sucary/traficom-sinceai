Licence class is not important; deal them as "MUUT" ("others") if you want to some identification. radio parameters are what matters most (and "station number" to map to the original data)


You mean BC stations with 9 kHz channel width and 10k transmission bandwidth? Real bandwidth used is 9 kHz (i.e. full transmission should fit into 9 kHz channel used); even though non-European use is in 10 kHz channels, and therefore receivers are receiving wider bandwidth, i.e. receive also possible interference outside the intended channel, and in interference calculations 10 kHz is more optimal. 

Even though, for this purpose, both 9 or 10 kHz used are relevant, choose either one.

(edit after this:)

Or were there similar mismatches in other rows (which station number?)

-> Yes, there were indeed; f. ex. station no. 440557 which have channel bw of 2500 kHz and transmission bw of 118600k; TYPO (copy-paste accident) during creation of dataset. Use SMALLER transmission bandwidth if channel bandwidth and transmission bandwidth mismatch. Can be used also on 9/10 kHz cases, for clarity. 


Question elsewhere: What counts as a "concern" in your manual 3074/3076 analysis: any frequency overlap with Finnish use, or only a calculated exceedance (pfd or field strength above a limit)?

-> Exceedance of the defined limit is definately concern; also close-by exceedance or semi-high pfd near the frequency might trigger a concern. Also these triggers may lower if Finnish use is using high-gain antennas and the source is in direct line towards the transmitter (possible)  location in IFIC. But for 3074/3076 analysis purposes there should be several cases which are foundable clearly.

Question elsewhere: Finland's AP30/30A/30B plan positions: the plan tables are empty in the IFIC download. Could you share Finland's reserved positions (orbital position, service area, band)?

-> Great question and good detective work! The Finnish GSO satellite filings can be found using the ITU Space Explorer where you can filter the notifying administration to Finland and choosing only Geostationary filings. All satellite filings notified to the ITU can be found there.  Mind you that those are frequency and orbital information and one filing can contain multiple satellites. ： https://www.itu.int/itu-r/space/apps/public/spaceexplorer/networks-explorer


Q:As the protection criterion we use the power flux-density (PFD) limits for space stations in RR Article 21, Table 21-4. Example: 3 400–4 200 MHz, GSO, −152 dB(W/m²) in 4 kHz at 0–5° elevation. You said that exceeding the defined limit is a concern. Is Table 21-4 the defined limit for the stations in the table, or is there another one (a national limit, or I/N)? If another, which value and source?

The PFD limit table found in the RR is the limit that is internationally agreed on and the main source of information. We also encourage to search for other sources along with the RR, since CEPT for instance can elaborate on the defined limits in Europe as you might want to focus on concerns instead of just hard limits. (Countries might have their own defined limits for some specific bands, but that is not relevant this time) 



We treat the delivered Excel table (Frequencies of interest, 874 stations) as the list of Finnish stations to be protected. So we check satellite downlinks (space-to-Earth) against each station's RX frequency and location. Is that correct?

-> Satellite downlink (space-to-Earth) is the interferer. Protected is the Finnish usage, i.e. RX frequencies in table, in some cases TX frequencies (if RX frequencies are not separately noted) is the ones to be protected. Note also, that TX frequencies are generally received in Finland (f. ex. BC and TV stations are received all around the transmitters, with even high gain antennas, fixed use have another end of the linki (i.e. receiving TX frequency of the link transmitter in the excel)) so possible high pfd's within Finland territory might raise concern. 

For broadcasting rows (Class of licence BC and BT), TX and RX frequency are the same. Should we protect only the transmitter site, or the whole coverage area around it?

-> Whole coverage area around them, see previous note. General rule: every TX is received in Finland.

Q: In the free IFIC 3074 database the beam table (s_beam) has no boresight coordinates and no beam axes, so we cannot tell where a satellite beam points. We therefore assume the worst case: the beam's peak gain is aimed at the Finnish station. This gives an upper bound, not a prediction, and can over-flag cases. Is this acceptable for screening? Or can you provide the beam data (GIMS graphical data) for the relevant notices?

A: The beams of the emission are not relevant and in the analysis the worst case scenario should always be assumed. The satellites move, spin, and might change their pointing direction constantly relative to Earth's surface (except GSO satellites).

For the terrestrial land-mobile side quest we calculate the field strength from each foreign station with ITU-R P.1546 and compare it with the ECC T/R 25-08 trigger field strengths. Where should we calculate it: at points on the Finnish border or coastline, or at the station locations in your Excel table? If at the border, which points matter most?

The brief says the processed results for IFIC 3074 and 3076 must be submitted as separate files, but does not define the format. Our plan: one CSV per IFIC with one row per notice (notice ID, administration, frequency, result class, PFD or field strength, margin, reason), plus the case cards as JSON. Is that fine, or do you expect another format, for example the same MDB format as the IFIC? Which fields are mandatory?

-> Xls/csv or doc/pdf export preferred (for quick evaluation purposes), but of course technical output of your choice is plus. I personally prefer JSON over MDB, but generally any machine readable open format is fine.

May we show rows of the delivered Excel table and an unfinished prototype in the demo video?

-> Yes, as you see best.

Regarding the terrestrial land-mobile side quest, the field strength should be calculated at points along the Finnish border, as we want to assess cross-border coordination against the ECC T/R 25-08 trigger thresholds.

For the border assessment, particular attention should be given to points closest to the foreign transmitters and along border sections where propagation conditions could result in the highest field strengths. The assessment should cover the relevant border sections rather than relying on a single representative point.

In addition, any Finnish station listed in the Excel table that are exposed to field strengths exceeding the applicable coordination thresholds should be flagged.

Question elsewhere: Above 470 MHz (terrestrial): T/R 25-08 stops at 470 MHz, and 81% of the land-mobile records in 3076 are above it. Which criterion do you use there?

-> That's a very good catch! For frequencies above 470 MHz, you can apply the same criteria as those specified in CEPT Recommendation T/R 25-08 for the frequency range above 400 MHz.

Great questions! 

For this challenge, you can use the general land-mobile threshold given in T/R 25-08 A.1.2.3

The assessment should be carried out along the Finnish land borders as well as along the outer limit of Finland's territorial sea.

The side quest is limited to land-mobile only.

T/R 25-08 threshold. ITU-R BR IFIC terrestrial preface defines station classes in land mobile service https://www.itu.int/en/itu-r/terrestrial/brific/brific/preface/preface_en.pdf. You should not need class of licence.

Using P.1546-6 is perfectly acceptable for final basis.

we dont need to apply correction in this challenge, e.g. apply the practical 10 dB correction (T/R 25-08 Annex 4) from 10 m to 3 m receiving height, and to which services. not needed.

An evaluation grid across Finland is good and an acceptable solution.

Are there specific satellite bands or notice types you suggest prioritizing for a validated worst-case PFD demonstration? -> There are no bands, at least within the synthetic "real-world" data, that should be prioritized above one or the other.

