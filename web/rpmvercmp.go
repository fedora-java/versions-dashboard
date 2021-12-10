package main

type Version string

// From rpmio/rpmvercmp.c
// https://github.com/rpm-software-management/rpm/blob/master/rpmio/rpmvercmp.c

/* compare alpha and numeric segments of two versions */
/* return 1: a is newer than b */
/*        0: a and b are the same version */
/*       -1: b is newer than a */
func (a Version) RpmVerCmp(b Version) int {

	/* easy comparison to see if versions are identical */
	if a == b {
		return 0
	}

	// From rpmio/rpmstring.h
	// https://github.com/rpm-software-management/rpm/blob/master/rpmio/rpmstring.h
	rislower := func(c rune) bool { return c >= 'a' && c <= 'z' }
	risupper := func(c rune) bool { return c >= 'A' && c <= 'Z' }
	risalpha := func(c rune) bool { return rislower(c) || risupper(c) }
	risdigit := func(c rune) bool { return c >= '0' && c <= '9' }
	risalnum := func(c rune) bool { return risalpha(c) || risdigit(c) }

	abuf, bbuf := append([]rune(a), 0), append([]rune(b), 0)
	str1, str2 := 0, 0
	one, two := str1, str2

	/* loop through each version segment of str1 and str2 and compare them */
	for abuf[one] != 0 || bbuf[two] != 0 {
		for abuf[one] != 0 && !risalnum(abuf[one]) && abuf[one] != '~' && abuf[one] != '^' {
			one++
		}
		for bbuf[two] != 0 && !risalnum(bbuf[two]) && bbuf[two] != '~' && bbuf[two] != '^' {
			two++
		}

		/* handle the tilde separator, it sorts before everything else */
		if abuf[one] == '~' || bbuf[two] == '~' {
			if abuf[one] != '~' {
				return 1
			}
			if bbuf[two] != '~' {
				return -1
			}
			one++
			two++
			continue
		}

		/*
		 * Handle caret separator. Concept is the same as tilde,
		 * except that if one of the strings ends (base version),
		 * the other is considered as higher version.
		 */
		if abuf[one] == '^' || bbuf[two] == '^' {
			if abuf[one] == 0 {
				return -1
			}
			if bbuf[two] == 0 {
				return 1
			}
			if abuf[one] != '^' {
				return 1
			}
			if bbuf[two] != '^' {
				return -1
			}
			one++
			two++
			continue
		}

		/* If we ran to the end of either, we are finished with the loop */
		if abuf[one] == 0 || bbuf[two] == 0 {
			break
		}

		str1 = one
		str2 = two

		/* grab first completely alpha or completely numeric segment */
		/* leave one and two pointing to the start of the alpha or numeric */
		/* segment and walk str1 and str2 to end of segment */
		var isnum bool
		if risdigit(abuf[str1]) {
			for risdigit(abuf[str1]) {
				str1++
			}
			for risdigit(bbuf[str2]) {
				str2++
			}
			isnum = true
		} else {
			for risalpha(abuf[str1]) {
				str1++
			}
			for risalpha(bbuf[str2]) {
				str2++
			}
			isnum = false
		}

		/* take care of the case where the two version segments are */
		/* different types: one numeric, the other alpha (i.e. empty) */
		/* numeric segments are always newer than alpha segments */
		/* XXX See patch #60884 (and details) from bugzilla #50977. */
		if two == str2 {
			if isnum {
				return 1
			} else {
				return -1
			}
		}

		if isnum {
			/* this used to be done by converting the digit segments */
			/* to ints using atoi() - it's changed because long  */
			/* digit segments can overflow an int - this should fix that. */

			/* throw away any leading zeros - it's a number, right? */
			for abuf[one] == '0' {
				one++
			}
			for bbuf[two] == '0' {
				two++
			}

			/* whichever number has more digits wins */
			onelen := str1 - one
			twolen := str2 - two
			if onelen > twolen {
				return 1
			}
			if twolen > onelen {
				return -1
			}
		}

		/* strcmp will return which one is greater - even if the two */
		/* segments are alpha or if they are numeric.  don't return  */
		/* if they are equal because there might be more segments to */
		/* compare */
		if string(abuf[one:str1]) < string(bbuf[two:str2]) {
			return -1
		}
		if string(abuf[one:str1]) > string(bbuf[two:str2]) {
			return 1
		}

		one = str1
		two = str2
	}

	/* this catches the case where all numeric and alpha segments have */
	/* compared identically but the segment sepparating characters were */
	/* different */
	if abuf[one] == 0 && bbuf[two] == 0 {
		return 0
	}

	/* whichever version still has characters left over wins */
	if abuf[one] == 0 {
		return -1
	} else {
		return 1
	}
}
