"""Deterministic reference Java file edits for sanity and demo traces."""

from __future__ import annotations

from legacy_cobol_env.server.task_bank import TaskInstance


MIGRATION_SERVICE_PATH = "src/main/java/com/example/migration/MigrationService.java"


PYTHON_SOLUTIONS_BY_FAMILY = {
    "decimal_copybook_payroll": r'''
from decimal import Decimal, ROUND_HALF_UP


def migrate(input_record: str) -> str:
    emp_id = input_record[0:6]
    emp_name = input_record[6:18]
    gross = Decimal(int(input_record[18:27])) / Decimal("100")
    tax_rate = Decimal(int(input_record[27:31])) / Decimal("1000")
    raw_deductions = input_record[31:39]
    sign = -1 if raw_deductions[0] == "-" else 1
    deductions = Decimal(sign * int(raw_deductions[1:])) / Decimal("100")
    tax = (gross * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net = gross - tax - deductions
    if input_record[39:40] == "Y":
        net += Decimal("50.00")
    if net < 0:
        net = Decimal("0.00")
    if net >= Decimal("5000.00"):
        category = "H"
    elif net >= Decimal("2500.00"):
        category = "M"
    else:
        category = "L"
    cents = int((net * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{emp_id}{emp_name[:12].ljust(12)}{cents:09d}{category}"
''',
    "fixed_width_customer": r'''
def migrate(input_record: str) -> str:
    cust_id = input_record[0:5]
    first = input_record[5:15].rstrip()
    last = input_record[15:27].rstrip()
    zip_code = input_record[27:32]
    status = {"A": "O", "S": "S"}.get(input_record[32:33], "C")
    balance = int(input_record[33:40])
    full_name = f"{last}, {first}"[:22].ljust(22)
    return f"{cust_id}{full_name}{zip_code}{status}{balance:08d}"
''',
    "claims_eligibility_branching": r'''
def migrate(input_record: str) -> str:
    claim_id = input_record[0:6]
    age = int(input_record[6:9])
    plan = input_record[9:10]
    days = int(input_record[10:13])
    preauth = input_record[13:14]
    amount_cents = int(input_record[14:21])
    if age < 18:
        decision, reason = "D", "A1"
    elif plan == "B" and amount_cents > 150000:
        decision, reason = "R", "B2"
    elif preauth == "N" and amount_cents > 100000:
        decision, reason = "D", "P1"
    elif days > 30:
        decision, reason = "R", "L1"
    else:
        decision, reason = "A", "OK"
    return f"{claim_id}{decision}{reason}"
''',
    "account_status_level88": r'''
def migrate(input_record: str) -> str:
    account_id = input_record[0:6]
    status = input_record[6:7]
    raw_balance = input_record[7:16]
    sign = -1 if raw_balance[0] == "-" else 1
    balance_cents = sign * int(raw_balance[1:])
    days = int(input_record[16:19])
    if status == "C":
        category, action = "CL", "N"
    elif status == "F":
        category, action = "FR", "H"
    elif days >= 90:
        category, action = "DL", "C"
    elif balance_cents < 0:
        category, action = "OD", "R"
    else:
        category, action = "OK", "N"
    return f"{account_id}{category}{action}"
''',
    "invoice_occurs_totals": r'''
from decimal import Decimal, ROUND_HALF_UP


def migrate(input_record: str) -> str:
    invoice_id = input_record[0:6]
    count = min(int(input_record[6:8]), 4)
    tax_rates = {
        "S": Decimal("0.0725"),
        "R": Decimal("0.0250"),
        "L": Decimal("0.1000"),
    }
    total = Decimal("0.00")
    for idx in range(count):
        start = 8 + idx * 9
        qty = int(input_record[start:start + 2])
        price = Decimal(int(input_record[start + 2:start + 8])) / Decimal("100")
        tax_code = input_record[start + 8:start + 9]
        line = (Decimal(qty) * price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax = (line * tax_rates.get(tax_code, Decimal("0.0000"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        line += tax
        total += line
    cents = int((total * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    flag = "H" if total >= Decimal("1000.00") else "L"
    return f"{invoice_id}{cents:09d}{count:02d}{flag}"
''',
    "date_normalization": r'''
def is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def valid_date(year: int, month: int, day: int) -> bool:
    month_lengths = [31, 29 if is_leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return 1 <= month <= 12 and 1 <= day <= month_lengths[month - 1]


def migrate(input_record: str) -> str:
    policy_id = input_record[0:6]
    raw = input_record[6:12]
    window = int(input_record[12:14])
    amount = input_record[14:21]
    yy = int(raw[0:2])
    mm = int(raw[2:4])
    dd = int(raw[4:6])
    year = 1900 + yy if yy >= window else 2000 + yy
    normalized = f"{year:04d}{mm:02d}{dd:02d}" if valid_date(year, mm, dd) else "00000000"
    valid = "Y" if normalized != "00000000" else "N"
    return f"{policy_id}{normalized}{valid}{amount}"
''',
}


PAYROLL_SERVICE = r'''
package com.example.migration;

import java.math.BigDecimal;
import java.math.RoundingMode;

public final class MigrationService {
    public String migrate(String inputRecord) {
        String empId = inputRecord.substring(0, 6);
        String empName = inputRecord.substring(6, 18);
        BigDecimal gross = new BigDecimal(Integer.parseInt(inputRecord.substring(18, 27))).movePointLeft(2);
        BigDecimal taxRate = new BigDecimal(Integer.parseInt(inputRecord.substring(27, 31))).movePointLeft(3);
        String rawDeductions = inputRecord.substring(31, 39);
        int sign = rawDeductions.charAt(0) == '-' ? -1 : 1;
        BigDecimal deductions = new BigDecimal(sign * Long.parseLong(rawDeductions.substring(1))).movePointLeft(2);
        BigDecimal tax = gross.multiply(taxRate).setScale(2, RoundingMode.HALF_UP);
        BigDecimal net = gross.subtract(tax).subtract(deductions);
        if ("Y".equals(inputRecord.substring(39, 40))) {
            net = net.add(new BigDecimal("50.00"));
        }
        if (net.compareTo(BigDecimal.ZERO) < 0) {
            net = BigDecimal.ZERO.setScale(2);
        }
        String category = net.compareTo(new BigDecimal("5000.00")) >= 0 ? "H" : net.compareTo(new BigDecimal("2500.00")) >= 0 ? "M" : "L";
        long cents = net.movePointRight(2).setScale(0, RoundingMode.HALF_UP).longValueExact();
        return empId + padRight(empName, 12) + String.format("%09d", cents) + category;
    }

    private static String padRight(String value, int width) {
        String clipped = value.length() > width ? value.substring(0, width) : value;
        return String.format("%-" + width + "s", clipped);
    }
}
'''


CUSTOMER_SERVICE = r'''
package com.example.migration;

import java.math.BigDecimal;

public final class MigrationService {
    public String migrate(String inputRecord) {
        String custId = inputRecord.substring(0, 5);
        String first = inputRecord.substring(5, 15).stripTrailing();
        String last = inputRecord.substring(15, 27).stripTrailing();
        String zipCode = inputRecord.substring(27, 32);
        String rawStatus = inputRecord.substring(32, 33);
        BigDecimal balance = new BigDecimal(Integer.parseInt(inputRecord.substring(33, 40))).movePointLeft(2);
        String status = rawStatus.equals("A") ? "O" : rawStatus.equals("S") ? "S" : "C";
        String fullName = padRight(last + ", " + first, 22);
        long cents = balance.movePointRight(2).longValueExact();
        return custId + fullName + zipCode + status + String.format("%08d", cents);
    }

    private static String padRight(String value, int width) {
        String clipped = value.length() > width ? value.substring(0, width) : value;
        return String.format("%-" + width + "s", clipped);
    }
}
'''


CLAIMS_SERVICE = r'''
package com.example.migration;

import java.math.BigDecimal;

public final class MigrationService {
    public String migrate(String inputRecord) {
        String claimId = inputRecord.substring(0, 6);
        int age = Integer.parseInt(inputRecord.substring(6, 9));
        String plan = inputRecord.substring(9, 10);
        int days = Integer.parseInt(inputRecord.substring(10, 13));
        String preauth = inputRecord.substring(13, 14);
        BigDecimal amount = new BigDecimal(Integer.parseInt(inputRecord.substring(14, 21))).movePointLeft(2);
        String decision;
        String reason;
        if (age < 18) {
            decision = "D";
            reason = "A1";
        } else if (plan.equals("B") && amount.compareTo(new BigDecimal("1500.00")) > 0) {
            decision = "R";
            reason = "B2";
        } else if (preauth.equals("N") && amount.compareTo(new BigDecimal("1000.00")) > 0) {
            decision = "D";
            reason = "P1";
        } else if (days > 30) {
            decision = "R";
            reason = "L1";
        } else {
            decision = "A";
            reason = "OK";
        }
        return claimId + decision + reason;
    }
}
'''


ACCOUNT_SERVICE = r'''
package com.example.migration;

import java.math.BigDecimal;

public final class MigrationService {
    public String migrate(String inputRecord) {
        String accountId = inputRecord.substring(0, 6);
        String status = inputRecord.substring(6, 7);
        String rawBalance = inputRecord.substring(7, 16);
        int sign = rawBalance.charAt(0) == '-' ? -1 : 1;
        BigDecimal balance = new BigDecimal(sign * Long.parseLong(rawBalance.substring(1))).movePointLeft(2);
        int days = Integer.parseInt(inputRecord.substring(16, 19));
        String category;
        String action;
        if (status.equals("C")) {
            category = "CL";
            action = "N";
        } else if (status.equals("F")) {
            category = "FR";
            action = "H";
        } else if (days >= 90) {
            category = "DL";
            action = "C";
        } else if (balance.compareTo(BigDecimal.ZERO) < 0) {
            category = "OD";
            action = "R";
        } else {
            category = "OK";
            action = "N";
        }
        return accountId + category + action;
    }
}
'''


INVOICE_SERVICE = r'''
package com.example.migration;

import java.math.BigDecimal;
import java.math.RoundingMode;

public final class MigrationService {
    public String migrate(String inputRecord) {
        String invoiceId = inputRecord.substring(0, 6);
        int count = Math.min(Integer.parseInt(inputRecord.substring(6, 8)), 4);
        BigDecimal total = BigDecimal.ZERO.setScale(2);
        for (int idx = 0; idx < count; idx++) {
            int start = 8 + idx * 9;
            int qty = Integer.parseInt(inputRecord.substring(start, start + 2));
            BigDecimal price = new BigDecimal(Integer.parseInt(inputRecord.substring(start + 2, start + 8))).movePointLeft(2);
            String taxCode = inputRecord.substring(start + 8, start + 9);
            BigDecimal line = new BigDecimal(qty).multiply(price).setScale(2, RoundingMode.HALF_UP);
            BigDecimal tax = line.multiply(taxRate(taxCode)).setScale(2, RoundingMode.HALF_UP);
            total = total.add(line.add(tax));
        }
        long cents = total.movePointRight(2).setScale(0, RoundingMode.HALF_UP).longValueExact();
        String flag = total.compareTo(new BigDecimal("1000.00")) >= 0 ? "H" : "L";
        return invoiceId + String.format("%09d", cents) + String.format("%02d", count) + flag;
    }

    private static BigDecimal taxRate(String taxCode) {
        if (taxCode.equals("S")) {
            return new BigDecimal("0.0725");
        }
        if (taxCode.equals("R")) {
            return new BigDecimal("0.0250");
        }
        if (taxCode.equals("L")) {
            return new BigDecimal("0.1000");
        }
        return BigDecimal.ZERO.setScale(4);
    }
}
'''


DATE_SERVICE = r'''
package com.example.migration;

import java.math.BigDecimal;

public final class MigrationService {
    public String migrate(String inputRecord) {
        String policyId = inputRecord.substring(0, 6);
        String raw = inputRecord.substring(6, 12);
        int window = Integer.parseInt(inputRecord.substring(12, 14));
        String amount = inputRecord.substring(14, 21);
        BigDecimal parsedAmount = new BigDecimal(Integer.parseInt(amount)).movePointLeft(2);
        if (parsedAmount.compareTo(BigDecimal.ZERO) < 0) {
            throw new IllegalArgumentException("amount cannot be negative");
        }
        int yy = Integer.parseInt(raw.substring(0, 2));
        int mm = Integer.parseInt(raw.substring(2, 4));
        int dd = Integer.parseInt(raw.substring(4, 6));
        int year = yy >= window ? 1900 + yy : 2000 + yy;
        String normalized = validDate(year, mm, dd) ? String.format("%04d%02d%02d", year, mm, dd) : "00000000";
        String valid = normalized.equals("00000000") ? "N" : "Y";
        return policyId + normalized + valid + amount;
    }

    private static boolean validDate(int year, int month, int day) {
        if (month < 1 || month > 12) {
            return false;
        }
        int[] lengths = {31, isLeap(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
        return day >= 1 && day <= lengths[month - 1];
    }

    private static boolean isLeap(int year) {
        return year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    }
}
'''


JAVA_FILES_BY_FAMILY = {
    "decimal_copybook_payroll": {MIGRATION_SERVICE_PATH: PAYROLL_SERVICE.strip() + "\n"},
    "fixed_width_customer": {MIGRATION_SERVICE_PATH: CUSTOMER_SERVICE.strip() + "\n"},
    "claims_eligibility_branching": {MIGRATION_SERVICE_PATH: CLAIMS_SERVICE.strip() + "\n"},
    "account_status_level88": {MIGRATION_SERVICE_PATH: ACCOUNT_SERVICE.strip() + "\n"},
    "invoice_occurs_totals": {MIGRATION_SERVICE_PATH: INVOICE_SERVICE.strip() + "\n"},
    "date_normalization": {MIGRATION_SERVICE_PATH: DATE_SERVICE.strip() + "\n"},
}


def java_files_for_task(task: TaskInstance) -> dict[str, str]:
    try:
        return dict(JAVA_FILES_BY_FAMILY[task.family_id])
    except KeyError as exc:
        raise ValueError(f"no Java oracle solution for family: {task.family_id}") from exc


def java_response_for_task(task: TaskInstance) -> dict[str, dict[str, str]]:
    return {"files": java_files_for_task(task)}


def solution_for_task(task: TaskInstance) -> str:
    """Return the legacy Python oracle solution for untouched training code."""
    try:
        return PYTHON_SOLUTIONS_BY_FAMILY[task.family_id].strip() + "\n"
    except KeyError as exc:
        raise ValueError(f"no Python oracle solution for family: {task.family_id}") from exc
