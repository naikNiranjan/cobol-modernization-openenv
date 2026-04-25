package com.example.migration;

import java.math.BigDecimal;

public final class RecordParser {
    private final String record;

    public RecordParser(String record) {
        this.record = record;
    }

    public String text(int start, int end) {
        return record.substring(start, end);
    }

    public BigDecimal unsignedImpliedDecimal(int start, int end, int scale) {
        return new BigDecimal(record.substring(start, end)).movePointLeft(scale);
    }

    public BigDecimal signedLeadingImpliedDecimal(int start, int end, int scale) {
        String raw = record.substring(start, end);
        int sign = raw.charAt(0) == '-' ? -1 : 1;
        return new BigDecimal(sign * Long.parseLong(raw.substring(1))).movePointLeft(scale);
    }
}
