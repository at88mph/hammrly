import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { searchSoftware } from "../api/catalog.js";
import { getConfig } from "../auth/config.js";
import { isInteractiveCatalogItem } from "../utils.js";

/**
 * @param {string} searchText
 * @param {'all' | 'desktop' | 'notebook' | 'carta'} kindFilter
 */
export function useSoftwareSearch(searchText, kindFilter) {
  const userTerms = useMemo(
    () => searchText.trim().split(/\s+/).filter(Boolean),
    [searchText],
  );

  const terms = useMemo(() => {
    if (userTerms.length > 0) return userTerms;
    try {
      return getConfig().defaultSearchTerms ?? [];
    } catch {
      return [];
    }
  }, [userTerms]);

  const query = useQuery({
    queryKey: ["softwareSearch", terms, kindFilter],
    queryFn: () => searchSoftware({ terms, limit: 50, offset: 0 }),
    enabled: terms.length > 0,
    staleTime: 30_000,
  });

  const filteredItems = useMemo(() => {
    const items = query.data?.items ?? [];
    return items.filter((item) => isInteractiveCatalogItem(item, kindFilter));
  }, [query.data, kindFilter]);

  return { ...query, filteredItems };
}

/**
 * @param {number} [debounceMs=300]
 */
export function useDebouncedValue(value, debounceMs = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), debounceMs);
    return () => clearTimeout(t);
  }, [value, debounceMs]);
  return debounced;
}
