package com.example.migration;

import java.math.BigDecimal;
import java.math.RoundingMode;

public final class RecordFormatter {
    public String padRight(String value, int width) {
        String clipped = value.length() > width ? value.substring(0, width) : value;
        return String.format("%-" + width + "s", clipped);
    }

    public String zeroPaddedCents(BigDecimal amount, int width) {
        long cents = amount.movePointRight(2).setScale(0, RoundingMode.HALF_UP).longValueExact();
        return String.format("%0" + width + "d", cents);
    }
}
