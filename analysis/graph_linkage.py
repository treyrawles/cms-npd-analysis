#!/usr/bin/env python3
"""
CMS National Provider Directory — Cross-Resource Graph Linkage Analysis
Runs on GitHub Actions with full 27.2M record dataset.
Outputs: graph_stats.json with complete linkage statistics.
"""

import json
import zstandard as zstd
import os
import sys
from collections import defaultdict, Counter
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'results')
os.makedirs(RESULTS_DIR, exist_ok=True)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def stream_file(filename, limit=None):
    path = os.path.join(DATA_DIR, filename)
    dctx = zstd.ZstdDecompressor()
    with open(path, 'rb') as f:
        with dctx.stream_reader(f) as reader:
            buf = b''
            count = 0
            while True:
                chunk = reader.read(1024 * 1024)
                if not chunk:
                    if buf.strip():
                        try:
                            yield json.loads(buf.decode('utf-8', errors='replace'))
                            count += 1
                        except:
                            pass
                    break
                buf += chunk
                lines = buf.split(b'\n')
                buf = lines[-1]
                for line in lines[:-1]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line.decode('utf-8', errors='replace'))
                        count += 1
                        if limit and count >= limit:
                            return
                    except:
                        continue

def main():
    stats = {}

    # =========================================================
    # STEP 1: Build Practitioner NPI → internal ID map
    # =========================================================
    log("STEP 1: Building Practitioner NPI map...")
    practitioner_npis = {}   # npi -> resource_id
    practitioner_ids = set()  # all resource IDs
    npi_to_id = {}

    for i, rec in enumerate(stream_file('Practitioner.ndjson.zst')):
        rid = rec.get('id', '')
        practitioner_ids.add(rid)
        for ident in rec.get('identifier', []):
            if ident.get('system', '') == 'http://hl7.org/fhir/sid/us-npi':
                npi = ident.get('value', '')
                if npi:
                    practitioner_npis[npi] = rid
                    npi_to_id[rid] = npi
        if i % 500000 == 0:
            log(f"  Practitioner: {i:,} records processed, {len(practitioner_npis):,} NPIs mapped")

    log(f"  Total practitioners: {len(practitioner_ids):,}")
    log(f"  Total NPIs mapped: {len(practitioner_npis):,}")

    stats['practitioner_total'] = len(practitioner_ids)
    stats['practitioner_npi_count'] = len(practitioner_npis)

    # =========================================================
    # STEP 2: Build PractitionerRole linkage map
    # =========================================================
    log("STEP 2: Building PractitionerRole linkage map...")
    # Maps: practitioner_id -> list of org_ids
    pract_to_orgs = defaultdict(set)
    # Maps: practitioner_id -> list of location_ids
    pract_to_locations = defaultdict(set)
    # Maps: org_id -> set of practitioner_ids
    org_to_practs = defaultdict(set)
    # Role counts
    role_count = 0
    roles_with_pract = 0
    roles_with_org = 0
    roles_with_location = 0
    roles_with_all_three = 0
    specialty_counter = Counter()
    inactive_roles = 0

    for i, rec in enumerate(stream_file('PractitionerRole.ndjson.zst')):
        role_count += 1
        pract_ref = rec.get('practitioner', {}).get('reference', '')
        org_ref = rec.get('organization', {}).get('reference', '')
        location_refs = [l.get('reference', '') for l in rec.get('location', [])]
        active = rec.get('active', True)

        if not active:
            inactive_roles += 1

        pract_id = pract_ref.replace('Practitioner/', '') if pract_ref else ''
        org_id = org_ref.replace('Organization/', '') if org_ref else ''

        has_pract = bool(pract_id)
        has_org = bool(org_id)
        has_loc = bool(location_refs)

        if has_pract:
            roles_with_pract += 1
        if has_org:
            roles_with_org += 1
        if has_loc:
            roles_with_location += 1
        if has_pract and has_org and has_loc:
            roles_with_all_three += 1

        if has_pract and has_org:
            pract_to_orgs[pract_id].add(org_id)
            org_to_practs[org_id].add(pract_id)
        if has_pract and has_loc:
            for loc in location_refs:
                loc_id = loc.replace('Location/', '')
                pract_to_locations[pract_id].add(loc_id)

        # Specialty
        for spec in rec.get('specialty', []):
            for coding in spec.get('coding', []):
                text = coding.get('display', coding.get('code', ''))
                if text:
                    specialty_counter[text] += 1

        if i % 500000 == 0:
            log(f"  PractitionerRole: {i:,} records, {len(pract_to_orgs):,} practitioners linked to orgs")

    log(f"  Total roles: {role_count:,}")
    log(f"  Roles with practitioner ref: {roles_with_pract:,}")
    log(f"  Roles with org ref: {roles_with_org:,}")
    log(f"  Roles with location ref: {roles_with_location:,}")
    log(f"  Roles with all three: {roles_with_all_three:,}")
    log(f"  Inactive roles: {inactive_roles:,}")

    stats['role_total'] = role_count
    stats['roles_with_practitioner'] = roles_with_pract
    stats['roles_with_organization'] = roles_with_org
    stats['roles_with_location'] = roles_with_location
    stats['roles_with_all_three'] = roles_with_all_three
    stats['inactive_roles'] = inactive_roles
    stats['top_specialties_from_roles'] = dict(specialty_counter.most_common(30))

    # =========================================================
    # STEP 3: Compute practitioner connectivity
    # =========================================================
    log("STEP 3: Computing practitioner connectivity...")
    practs_with_org = len(pract_to_orgs)
    practs_with_location = len(pract_to_locations)

    # Distribution: how many orgs per practitioner
    orgs_per_pract = Counter(len(v) for v in pract_to_orgs.values())
    locs_per_pract = Counter(len(v) for v in pract_to_locations.values())

    # Practitioners with no org link at all
    practs_no_org = len(practitioner_ids - set(pract_to_orgs.keys()))
    practs_no_location = len(practitioner_ids - set(pract_to_locations.keys()))

    log(f"  Practitioners linked to ≥1 org: {practs_with_org:,}")
    log(f"  Practitioners linked to ≥1 location: {practs_with_location:,}")
    log(f"  Practitioners with NO org link: {practs_no_org:,}")
    log(f"  Practitioners with NO location link: {practs_no_location:,}")

    stats['practitioners_with_org_link'] = practs_with_org
    stats['practitioners_with_location_link'] = practs_with_location
    stats['practitioners_no_org_link'] = practs_no_org
    stats['practitioners_no_location_link'] = practs_no_location
    stats['orgs_per_practitioner_dist'] = {str(k): v for k, v in sorted(orgs_per_pract.items())[:20]}
    stats['locations_per_practitioner_dist'] = {str(k): v for k, v in sorted(locs_per_pract.items())[:20]}

    # =========================================================
    # STEP 4: Top organizations by practitioner count
    # =========================================================
    log("STEP 4: Computing top organizations by practitioner count...")
    top_orgs_by_pract = Counter({k: len(v) for k, v in org_to_practs.items()})
    top_100_org_ids = [org_id for org_id, _ in top_orgs_by_pract.most_common(100)]
    top_100_counts = {org_id: count for org_id, count in top_orgs_by_pract.most_common(100)}

    log(f"  Total unique orgs with practitioners: {len(org_to_practs):,}")
    log(f"  Top org has {top_orgs_by_pract.most_common(1)[0][1]:,} practitioners")

    stats['unique_orgs_with_practitioners'] = len(org_to_practs)
    stats['top_100_org_ids_by_pract_count'] = top_100_counts

    # Org size distribution
    org_size_dist = Counter()
    for count in top_orgs_by_pract.values():
        if count == 1:
            org_size_dist['1'] += 1
        elif count <= 5:
            org_size_dist['2-5'] += 1
        elif count <= 10:
            org_size_dist['6-10'] += 1
        elif count <= 50:
            org_size_dist['11-50'] += 1
        elif count <= 100:
            org_size_dist['51-100'] += 1
        elif count <= 500:
            org_size_dist['101-500'] += 1
        elif count <= 1000:
            org_size_dist['501-1000'] += 1
        else:
            org_size_dist['1000+'] += 1

    stats['org_size_distribution'] = dict(org_size_dist)
    log(f"  Org size distribution: {dict(org_size_dist)}")

    # =========================================================
    # STEP 5: Look up organization names for top 100
    # =========================================================
    log("STEP 5: Looking up organization names for top 100...")
    top_org_names = {}
    top_org_set = set(top_100_org_ids)
    found = 0

    for rec in stream_file('Organization.ndjson.zst'):
        rid = rec.get('id', '')
        if rid in top_org_set:
            name = rec.get('name', 'Unknown')
            pract_count = top_100_counts.get(rid, 0)
            top_org_names[rid] = {'name': name, 'practitioner_count': pract_count}
            found += 1
            if found >= 100:
                break

    # Sort by practitioner count
    top_orgs_sorted = sorted(top_org_names.items(), key=lambda x: -x[1]['practitioner_count'])
    stats['top_50_organizations'] = [
        {'id': k, 'name': v['name'], 'practitioner_count': v['practitioner_count']}
        for k, v in top_orgs_sorted[:50]
    ]

    log("  Top 10 organizations by practitioner count:")
    for item in stats['top_50_organizations'][:10]:
        log(f"    {item['name']}: {item['practitioner_count']:,} practitioners")

    # =========================================================
    # STEP 6: Chain completeness analysis
    # =========================================================
    log("STEP 6: Computing full chain completeness (Practitioner→Role→Org→Location→Endpoint)...")

    # Build endpoint reference set from Practitioner extensions
    log("  Building endpoint reference set...")
    pract_with_endpoint = set()
    for rec in stream_file('Practitioner.ndjson.zst'):
        rid = rec.get('id', '')
        for ext in rec.get('extension', []):
            url = ext.get('url', '')
            if 'endpoint' in url.lower():
                val = ext.get('valueReference', {}).get('reference', '')
                if val:
                    pract_with_endpoint.add(rid)
                    break

    log(f"  Practitioners with endpoint ref: {len(pract_with_endpoint):,}")
    stats['practitioners_with_endpoint_ref'] = len(pract_with_endpoint)

    # Full chain: has org + has location + has endpoint
    pract_with_org_set = set(pract_to_orgs.keys())
    pract_with_loc_set = set(pract_to_locations.keys())

    full_chain = pract_with_org_set & pract_with_loc_set & pract_with_endpoint
    partial_chain_org_only = pract_with_org_set - pract_with_loc_set - pract_with_endpoint
    partial_chain_org_loc = (pract_with_org_set & pract_with_loc_set) - pract_with_endpoint
    no_chain = practitioner_ids - pract_with_org_set - pract_with_loc_set - pract_with_endpoint

    log(f"  Full chain (org+loc+endpoint): {len(full_chain):,} ({len(full_chain)/len(practitioner_ids)*100:.1f}%)")
    log(f"  Org+Loc only (no endpoint): {len(partial_chain_org_loc):,}")
    log(f"  Org only: {len(partial_chain_org_only):,}")
    log(f"  No chain at all: {len(no_chain):,}")

    stats['chain_completeness'] = {
        'full_chain_org_loc_endpoint': len(full_chain),
        'full_chain_pct': round(len(full_chain) / len(practitioner_ids) * 100, 2),
        'org_and_loc_no_endpoint': len(partial_chain_org_loc),
        'org_only': len(partial_chain_org_only),
        'no_chain': len(no_chain),
        'total_practitioners': len(practitioner_ids)
    }

    # =========================================================
    # STEP 7: OrganizationAffiliation network analysis
    # =========================================================
    log("STEP 7: Analyzing OrganizationAffiliation network...")
    org_aff_network = defaultdict(set)  # org -> set of participating orgs
    hie_orgs = set()
    member_orgs = set()
    aff_total = 0

    for rec in stream_file('OrganizationAffiliation.ndjson.zst'):
        aff_total += 1
        org_ref = rec.get('organization', {}).get('reference', '')
        part_ref = rec.get('participatingOrganization', {}).get('reference', '')
        codes = [c.get('code', '') for role in rec.get('code', []) for c in role.get('coding', [])]

        if org_ref and part_ref:
            org_aff_network[org_ref].add(part_ref)

        for code in codes:
            if 'HIE' in code or 'HIO' in code:
                hie_orgs.add(org_ref)
                hie_orgs.add(part_ref)
            if code == 'member':
                member_orgs.add(part_ref)

    # Network stats
    network_sizes = Counter(len(v) for v in org_aff_network.values())
    top_network_hubs = sorted(org_aff_network.items(), key=lambda x: -len(x[1]))[:20]

    log(f"  Total affiliation records: {aff_total:,}")
    log(f"  Unique org hubs: {len(org_aff_network):,}")
    log(f"  HIE/HIO orgs: {len(hie_orgs):,}")
    log(f"  Member orgs: {len(member_orgs):,}")

    stats['org_affiliation_network'] = {
        'total_records': aff_total,
        'unique_org_hubs': len(org_aff_network),
        'hie_hio_org_count': len(hie_orgs),
        'member_org_count': len(member_orgs),
        'network_size_distribution': {str(k): v for k, v in sorted(network_sizes.items())[:15]},
        'top_20_network_hubs': [
            {'org': hub, 'member_count': len(members)}
            for hub, members in top_network_hubs
        ]
    }

    # =========================================================
    # STEP 8: Summary statistics
    # =========================================================
    log("STEP 8: Computing summary statistics...")

    total_practitioners = len(practitioner_ids)
    pct_with_org = practs_with_org / total_practitioners * 100
    pct_with_loc = practs_with_location / total_practitioners * 100
    pct_with_endpoint = len(pract_with_endpoint) / total_practitioners * 100
    pct_full_chain = len(full_chain) / total_practitioners * 100

    stats['summary'] = {
        'total_practitioners': total_practitioners,
        'pct_linked_to_org': round(pct_with_org, 2),
        'pct_linked_to_location': round(pct_with_loc, 2),
        'pct_with_endpoint': round(pct_with_endpoint, 2),
        'pct_full_chain': round(pct_full_chain, 2),
        'unique_orgs_in_network': len(org_to_practs),
        'unique_orgs_with_practitioners': len(org_to_practs),
        'analysis_timestamp': datetime.now().isoformat()
    }

    log("\n=== FINAL SUMMARY ===")
    log(f"  Total practitioners: {total_practitioners:,}")
    log(f"  % linked to org: {pct_with_org:.1f}%")
    log(f"  % linked to location: {pct_with_loc:.1f}%")
    log(f"  % with endpoint: {pct_with_endpoint:.1f}%")
    log(f"  % full chain: {pct_full_chain:.1f}%")

    # Save results
    out_path = os.path.join(RESULTS_DIR, 'graph_stats.json')
    with open(out_path, 'w') as f:
        json.dump(stats, f, indent=2)
    log(f"\nResults saved to {out_path}")
    log("GRAPH LINKAGE ANALYSIS COMPLETE")

if __name__ == '__main__':
    main()
